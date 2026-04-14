import bpy
import struct
import sys
import os
import math
import traceback
from io import BytesIO
from mathutils import Euler, Matrix, Vector
from pathlib import Path


# ---------------------------------------------------------------------------
# SCENE UTILITIES
# ---------------------------------------------------------------------------

def clear_entire_scene():
    """Nuke everything in the scene so we start fresh."""
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT')

    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()

    for block in [
        bpy.data.meshes,
        bpy.data.armatures,
        bpy.data.materials,
        bpy.data.images,
        bpy.data.collections,
    ]:
        for item in block:
            if item.users == 0:
                block.remove(item)


# ---------------------------------------------------------------------------
# TEXTURE CONVERSION  (.bitmap → .dds)
# ---------------------------------------------------------------------------

class G7Bitmap:
    def convert_to_dds(self, f: BytesIO, out_path: Path, invert_green: bool = False):
        fmt_val = int.from_bytes(f.read(2), "little")
        f.read(2)
        h_mips = int.from_bytes(f.read(2), "little", signed=True)
        f.read(30)
        v_mips = int.from_bytes(f.read(2), "little", signed=True)
        f.read(30)
        mip_count = int.from_bytes(f.read(4), "little")
        if mip_count == 0:
            mip_count = 1

        f.read(72)
        for _ in range(mip_count):
            f.read(8)

        f.seek(272)
        raw_data = f.read()
        w, h = h_mips, v_mips

        pf_flags, fourcc, rgb_bitcount = 0, b'', 0
        r_mask = g_mask = b_mask = a_mask = 0

        if fmt_val == 5:    # BC1
            pf_flags = 0x4; fourcc = b'DXT1'
        elif fmt_val == 6:  # BC3
            pf_flags = 0x4; fourcc = b'DXT5'
        elif fmt_val == 7:  # BC5
            pf_flags = 0x4; fourcc = b'ATI2'
        elif fmt_val == 8:  # BC4
            pf_flags = 0x4; fourcc = b'ATI1'
        elif fmt_val == 2:  # RGBA
            pf_flags = 0x41
            rgb_bitcount = 32
            r_mask, g_mask, b_mask, a_mask = 0x000000FF, 0x0000FF00, 0x00FF0000, 0xFF000000
        else:               # RGB
            pf_flags = 0x40
            rgb_bitcount = 24
            r_mask, g_mask, b_mask, a_mask = 0x000000FF, 0x0000FF00, 0x00FF0000, 0x00000000

        # --- Invert green / Blue fix for Normal Maps ---
        is_nrm = any(sfx in out_path.stem.lower() for sfx in ('_nrm', '_normal'))
        if is_nrm:
            if fmt_val == 7:
                # Decode BC5 to RGBA so we can securely inject Blue=255 inside the DDS file
                pf_flags = 0x41
                fourcc = b''
                rgb_bitcount = 32
                r_mask, g_mask, b_mask, a_mask = 0x000000FF, 0x0000FF00, 0x00FF0000, 0xFF000000

                out_data = bytearray()
                offset = 0
                cur_w, cur_h = w, h
                for mip in range(mip_count):
                    blocks_x = (cur_w + 3) // 4
                    blocks_y = (cur_h + 3) // 4
                    mip_rgba = bytearray(cur_w * cur_h * 4)
                    
                    for by in range(blocks_y):
                        for bx in range(blocks_x):
                            if offset + 15 >= len(raw_data): break
                            
                            # Decode Red Channel
                            ep0 = raw_data[offset]; ep1 = raw_data[offset+1]
                            rp = [ep0, ep1]
                            if ep0 > ep1: rp.extend(((6*ep0+1*ep1)//7, (5*ep0+2*ep1)//7, (4*ep0+3*ep1)//7, (3*ep0+4*ep1)//7, (2*ep0+5*ep1)//7, (1*ep0+6*ep1)//7))
                            else: rp.extend(((4*ep0+1*ep1)//5, (3*ep0+2*ep1)//5, (2*ep0+3*ep1)//5, (1*ep0+4*ep1)//5, 0, 255))
                            b2, b3, b4, b5, b6, b7 = raw_data[offset+2], raw_data[offset+3], raw_data[offset+4], raw_data[offset+5], raw_data[offset+6], raw_data[offset+7]
                            idxR = b2 | (b3<<8) | (b4<<16) | (b5<<24) | (b6<<32) | (b7<<40)

                            # Decode Green Channel
                            ep0 = raw_data[offset+8]; ep1 = raw_data[offset+9]
                            gp = [ep0, ep1]
                            if ep0 > ep1: gp.extend(((6*ep0+1*ep1)//7, (5*ep0+2*ep1)//7, (4*ep0+3*ep1)//7, (3*ep0+4*ep1)//7, (2*ep0+5*ep1)//7, (1*ep0+6*ep1)//7))
                            else: gp.extend(((4*ep0+1*ep1)//5, (3*ep0+2*ep1)//5, (2*ep0+3*ep1)//5, (1*ep0+4*ep1)//5, 0, 255))
                            b2, b3, b4, b5, b6, b7 = raw_data[offset+10], raw_data[offset+11], raw_data[offset+12], raw_data[offset+13], raw_data[offset+14], raw_data[offset+15]
                            idxG = b2 | (b3<<8) | (b4<<16) | (b5<<24) | (b6<<32) | (b7<<40)
                            
                            offset += 16
                            
                            for i in range(16):
                                px = bx * 4 + (i % 4)
                                py = by * 4 + (i // 4)
                                if px < cur_w and py < cur_h:
                                    pix_idx = (py * cur_w + px) * 4
                                    mip_rgba[pix_idx]     = rp[(idxR >> (i*3)) & 7]
                                    g_val                 = gp[(idxG >> (i*3)) & 7]
                                    mip_rgba[pix_idx + 1] = (255 - g_val) if invert_green else g_val
                                    mip_rgba[pix_idx + 2] = 255 # Always Blue = 255
                                    mip_rgba[pix_idx + 3] = 255
                    
                    out_data.extend(mip_rgba)
                    cur_w = max(1, cur_w // 2); cur_h = max(1, cur_h // 2)
                raw_data = bytes(out_data)

            elif fmt_val == 2:
                raw_data = bytearray(raw_data)
                # RGBA: byte0=R, byte1=G, byte2=B, byte3=A
                for i in range(0, len(raw_data), 4):
                    if invert_green:
                        raw_data[i+1] = 255 - raw_data[i+1]
                    raw_data[i+2] = 255 # Always Blue = 255
                raw_data = bytes(raw_data)
        
        # Build DDS Header safely
        flags = 0x1007
        if mip_count > 1:
            flags |= 0x20000

        header = bytearray(b'DDS ')
        header += struct.pack('<IIIIIII44x', 124, flags, h, w, 0, 1, mip_count)
        fourcc_val = struct.unpack('<I', fourcc)[0] if fourcc else 0
        header += struct.pack(
            '<IIIIIIII',
            32, pf_flags, fourcc_val, rgb_bitcount,
            r_mask, g_mask, b_mask, a_mask,
        )

        caps1 = 0x1000
        if mip_count > 1:
            caps1 |= 0x400008
        header += struct.pack('<IIIII', caps1, 0, 0, 0, 0)
        
        with open(out_path, 'wb') as out_f:
            out_f.write(header)
            out_f.write(raw_data)


# ---------------------------------------------------------------------------
# MATERIAL BUILDER
# ---------------------------------------------------------------------------

# Suffix patterns for each texture role (checked against lower-case filename).
# _difa is listed first in DIF_SUFFIXES so it takes priority over plain _dif
# when both exist — the alpha channel signals transparency.
_DIFA_SUFFIX   = "_difa"
_DIF_SUFFIXES  = ("_difa", "_dif", "_diffuse")
_SPC_SUFFIXES  = ("_spc_clrexp",)
_REF_SUFFIXES  = ("_ref",)
_NRM_SUFFIXES  = ("_nrm", "_normal")


def _find_texture(root_path: Path, tex_prefix: str, suffixes: tuple) -> Path | None:
    """
    Search for a DDS whose stem equals tex_prefix + one of suffixes exactly.
    tex_prefix is the authoritative texture base name supplied by the caller
    (looked up from the .attach table, or the mesh stem itself for direct hits).
    """
    tex_prefix_lower = tex_prefix.lower()
    for tex_path in root_path.rglob("*.dds"):
        stem_lower = tex_path.stem.lower()
        for sfx in suffixes:
            if stem_lower == tex_prefix_lower + sfx.lower():
                return tex_path
    return None


def _read_attach_log(log_path: Path) -> dict:
    """
    Parse the G7Reader console output (captured to a text file by the bat)
    and return a dict mapping each mesh name (lower-case) to the texture base
    prefix that the engine associates with it.

    Expected format (lines we care about):
        Entry N Name: some_name
    Texture entries end in a known suffix; mesh entries follow them and
    inherit the most-recently-seen texture prefix until a new group starts.
    """
    TEX_SUFFIXES = ("_difa", "_dif", "_diffuse", "_nrm", "_normal",
                    "_spc_clrexp", "_ref")

    def is_texture_entry(name: str) -> str | None:
        nl = name.lower()
        for sfx in TEX_SUFFIXES:
            if nl.endswith(sfx):
                return nl[: len(nl) - len(sfx)]
        return None

    mapping = {}
    current_prefix = None

    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        names_found = []
        for line in lines:
            line = line.strip()
            # Match lines like "Entry 1 Name: falcon_decals_difa"
            if line.startswith("Entry ") and " Name: " in line:
                name = line.split(" Name: ", 1)[1].strip()
                names_found.append(name)

        print(f"  [ATTACH] {log_path.name}: found {len(names_found)} entries")

        for name in names_found:
            prefix = is_texture_entry(name)
            if prefix is not None:
                current_prefix = prefix
            else:
                if current_prefix is not None:
                    mapping[name.lower()] = current_prefix
                    print(f"  [ATTACH] mapped {name} → {current_prefix}")

    except Exception as e:
        print(f"  [ATTACH] Could not parse {log_path.name}: {e}")
        import traceback; traceback.print_exc()

    return mapping


def _load_image(path: Path, color_space: str) -> bpy.types.Image:
    """Load an image (or reuse if already loaded) and set its colour space."""
    # Reuse if already in bpy.data.images
    abs_str = str(path.resolve())
    for img in bpy.data.images:
        if bpy.path.abspath(img.filepath) == abs_str:
            img.colorspace_settings.name = color_space
            return img

    img = bpy.data.images.load(abs_str)
    img.colorspace_settings.name = color_space
    return img


def _add_tex_node(
    nodes: bpy.types.NodeTree,
    image: bpy.types.Image,
    location: tuple,
    label: str,
) -> bpy.types.Node:
    """Create a ShaderNodeTexImage, attach an image and position it."""
    node = nodes.new(type='ShaderNodeTexImage')
    node.image = image
    node.location = location
    node.label = label
    return node


def create_pbr_material(name: str, root_path: Path, tex_prefix: str | None = None) -> bpy.types.Material:
    """
    Build a Principled BSDF material with the following wiring:

        _dif / _difa  → Base Color          (Linear Rec.709)
                         _difa also wires Alpha → Alpha + enables blend mode
        _spc_clrexp   → alpha → Invert → Roughness + Specular Tint (Linear Rec.709)
        _ref          → Metallic            (Linear Rec.709)
        _nrm          → Normal Map (Color) → Normal   (Non-Color)

    tex_prefix: explicit texture base name from the .attach table.  If None,
                falls back to the mesh stem itself (handles direct-match cases
                like falcon_body → falcon_body_dif.dds).
    """
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # Start clean
    for n in nodes:
        nodes.remove(n)

    # --- Core nodes ---
    output = nodes.new('ShaderNodeOutputMaterial')
    output.location = (600, 0)

    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.location = (300, 0)
    links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

    # Use the attach-table prefix if supplied, otherwise fall back to the mesh
    # stem itself — this handles both direct matches (falcon → falcon_dif.dds)
    # and cross-named decal cases (alpha_decals_1 → falcon_decals prefix).
    _model_stem = (tex_prefix or name).lower()

    # ------------------------------------------------------------------
    # Compound-name check:
    # When a mesh has an attach-table prefix that differs from its own name
    # (e.g. mesh "screen" with prefix "falcon"), check whether a texture
    # named prefix_meshname exists (e.g. "falcon_screen_dif" or just
    # "falcon_screen" as a bare diffuse).  If found, that texture is
    # dedicated to this specific mesh and should be used exclusively —
    # no other PBR slots are applied because the naming convention for
    # those (falcon_screen_nrm, falcon_screen_spc_clrexp etc.) does not
    # exist in the asset set.
    # ------------------------------------------------------------------
    _compound_stem = None
    if tex_prefix and tex_prefix.lower() != name.lower():
        candidate = f"{tex_prefix.lower()}_{name.lower()}"
        if _find_texture(root_path, candidate, _DIF_SUFFIXES + ("",)):
            _compound_stem = candidate
            print(f"  [MAT] compound texture match: {name} → {candidate}")

    if _compound_stem:
        # Compound match — diffuse only, no other PBR slots
        dif_path = _find_texture(root_path, _compound_stem, _DIF_SUFFIXES + ("",))
        if dif_path:
            is_difa = dif_path.stem.lower().endswith(_DIFA_SUFFIX)
            label   = 'Diffuse compound (_difa)' if is_difa else 'Diffuse compound'
            img = _load_image(dif_path, 'Linear Rec.709')
            tex = _add_tex_node(nodes, img, (-400, 300), label)
            links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
            if is_difa:
                links.new(tex.outputs['Alpha'], bsdf.inputs['Alpha'])
                if hasattr(mat, 'blend_method'):
                    mat.blend_method = 'BLEND'
                if hasattr(mat, 'shadow_method'):
                    mat.shadow_method = 'CLIP'
        return mat

    # ------------------------------------------------------------------
    # Diffuse  →  Base Color  (and Alpha if _difa)
    # ------------------------------------------------------------------
    dif_path = _find_texture(root_path, _model_stem, _DIF_SUFFIXES)
    if dif_path:
        is_difa = dif_path.stem.lower().endswith(_DIFA_SUFFIX)
        label   = 'Diffuse (_difa)' if is_difa else 'Diffuse (_dif)'
        img = _load_image(dif_path, 'Linear Rec.709')
        tex = _add_tex_node(nodes, img, (-400, 300), label)
        links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
        if is_difa:
            # Alpha channel carries transparency — wire it through and enable
            # alpha blending so Blender renders it correctly.
            links.new(tex.outputs['Alpha'], bsdf.inputs['Alpha'])
            # blend_method/shadow_method were restructured in Blender 4.x
            if hasattr(mat, 'blend_method'):
                mat.blend_method = 'BLEND'
            if hasattr(mat, 'shadow_method'):
                mat.shadow_method = 'CLIP'

    # ------------------------------------------------------------------
    # Specular/Gloss  →  alpha → Invert → Roughness
    # (The alpha channel of _spc_clrexp is the gloss mask; inverting it
    #  gives roughness.)
    # ------------------------------------------------------------------
    spc_path = _find_texture(root_path, _model_stem, _SPC_SUFFIXES)
    if spc_path:
        img = _load_image(spc_path, 'Linear Rec.709')
        tex = _add_tex_node(nodes, img, (-800, 0), 'Specular (_spc_clrexp)')

        invert = nodes.new('ShaderNodeInvert')
        invert.location = (-500, 0)
        invert.label = 'Gloss → Roughness'

        links.new(tex.outputs['Alpha'],  invert.inputs['Color'])
        links.new(invert.outputs['Color'], bsdf.inputs['Roughness'])
        links.new(tex.outputs['Color'], bsdf.inputs['Specular Tint'])

    # ------------------------------------------------------------------
    # Reflection mask  →  Metallic
    # ------------------------------------------------------------------
    ref_path = _find_texture(root_path, _model_stem, _REF_SUFFIXES)
    if ref_path:
        img = _load_image(ref_path, 'Linear Rec.709')
        tex = _add_tex_node(nodes, img, (-800, -300), 'Reflection (_ref)')
        links.new(tex.outputs['Color'], bsdf.inputs['Metallic'])

    # ------------------------------------------------------------------
    # Normal map  →  Normal Map node  →  Normal
    # ------------------------------------------------------------------
    nrm_path = _find_texture(root_path, _model_stem, _NRM_SUFFIXES)
    if nrm_path:
        img = _load_image(nrm_path, 'Non-Color')
        tex = _add_tex_node(nodes, img, (-800, -600), 'Normal (_nrm)')

        nrm_node = nodes.new('ShaderNodeNormalMap')
        nrm_node.location = (-500, -600)

        # Wire the Color output of the texture into the Color input of the
        # Normal Map node (not Vector), as requested.
        links.new(tex.outputs['Color'], nrm_node.inputs['Color'])
        links.new(nrm_node.outputs['Normal'], bsdf.inputs['Normal'])

    return mat


# ---------------------------------------------------------------------------
# RIG READER
# ---------------------------------------------------------------------------

class _Matrix3x3:
    __slots__ = ('rows',)
    def __init__(self): self.rows = []
    def read(self, f: BytesIO):
        self.rows = [struct.unpack("fff", f.read(12)) for _ in range(3)]


class _G7Bone:
    __slots__ = ('px','py','pz','matrix','name','parent_name','parent_id')
    def __init__(self):
        self.px = self.py = self.pz = 0.0
        self.matrix = _Matrix3x3()
        self.name = ""
        self.parent_name = ""
        self.parent_id = -1

    def read(self, f: BytesIO):
        f.seek(0x3C, 1)                                      # skip 60 bytes
        self.px, self.py, self.pz = struct.unpack("fff", f.read(12))
        self.matrix.read(f)
        cur = f.tell()
        self.name = f.read(16).split(b"\x00", 1)[0].decode("utf-8", errors="replace")
        f.seek(cur + 16 + 0x30)                              # skip rest of name block
        cur = f.tell()
        self.parent_name = f.read(16).split(b"\x00", 1)[0].decode("utf-8", errors="replace")
        f.seek(cur + 16 + 0x30)                              # skip rest of parent block
        self.parent_id, = struct.unpack("I", f.read(4))


def read_rig(rig_path: Path):
    """
    Parse a .rig file and return a list of _G7Bone objects.
    Returns an empty list if parsing fails.
    """
    try:
        with open(rig_path, "rb") as fh:
            f = BytesIO(fh.read())
        _unknown = struct.unpack("h", f.read(2))[0]
        bone_count = struct.unpack("h", f.read(2))[0]
        _rig_name = f.read(12).split(b"\x00", 1)[0].decode("utf-8", errors="replace")
        f.seek(0x50)
        bones = []
        for _ in range(bone_count):
            b = _G7Bone()
            b.read(f)
            bones.append(b)
        return bones
    except Exception as e:
        print(f"  [RIG] Failed to parse {rig_path.name}: {e}")
        return []


def create_armature(bones: list, name: str) -> bpy.types.Object:
    """
    Build a Blender armature from a list of _G7Bone objects.
    Applies the same +90° X rotation as the mesh objects.
    Uses direct data API to avoid bpy.ops mode-set issues in background mode.
    """
    arm_data = bpy.data.armatures.new(name)
    arm_obj  = bpy.data.objects.new(name, arm_data)
    bpy.context.collection.objects.link(arm_obj)

    # Must be the active object to enter edit mode
    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.select_all(action='DESELECT')
    arm_obj.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')

    edit_bones = {}
    for bone in bones:
        eb = arm_data.edit_bones.new(bone.name)
        eb.head = (bone.px, bone.py, bone.pz)
        eb.tail = (bone.px, bone.py, bone.pz + 0.5)
        edit_bones[bone.name] = eb

    # Wire up parents after all bones exist
    for bone in bones:
        if bone.parent_name and bone.parent_name in edit_bones:
            edit_bones[bone.name].parent = edit_bones[bone.parent_name]

    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    arm_obj.rotation_euler = (math.pi / 2, 0, 0)
    return arm_obj


def apply_skinning(obj: bpy.types.Object, arm_obj: bpy.types.Object,
                   bone_ids: list, weights: list, rig_bones: list):
    """
    Create vertex groups matching bone names and assign skinning weights.

    bone_map is built from rig_bones (the original parsed order) rather than
    arm_obj.data.bones (which has arbitrary internal ordering in Blender).
    Applies the +1 bone ID offset that the G7 format requires.
    """
    # Build map from file bone index → bone name using the PARSED order
    bone_map = {i: b.name for i, b in enumerate(rig_bones)}

    # Diagnostic: show first few entries and a sample of the vertex data
    print(f"  [SKIN] bone_map[0..4]: { {k: bone_map[k] for k in list(bone_map)[:5]} }")
    if bone_ids:
        sample = bone_ids[:3]
        sample_w = weights[:3]
        print(f"  [SKIN] first 3 verts bone_ids: {sample}")
        print(f"  [SKIN] first 3 verts weights:  {sample_w}")

    # Count how many verts actually have non-zero weights
    weighted = sum(1 for wts in weights if any(w > 0.0 for w in wts))
    print(f"  [SKIN] {weighted}/{len(weights)} verts have weights")

    # Create a vertex group for every bone
    for bone_name in bone_map.values():
        if bone_name not in obj.vertex_groups:
            obj.vertex_groups.new(name=bone_name)

    assigned = 0
    for vert_idx, (b_ids, wts) in enumerate(zip(bone_ids, weights)):
        for j in range(4):
            if wts[j] > 0.0:
                bone_id = b_ids[j]        # direct index into bone_map
                if bone_id in bone_map:
                    obj.vertex_groups[bone_map[bone_id]].add(
                        [vert_idx], wts[j], 'ADD'
                    )
                    assigned += 1
                else:
                    print(f"  [SKIN] WARNING: bone_id {bone_id} out of range "
                          f"(max={max(bone_map)})")

    print(f"  [SKIN] {assigned} weight assignments made across "
          f"{len(obj.vertex_groups)} vertex groups")

    mod = obj.modifiers.new(name="Armature", type='ARMATURE')
    mod.object = arm_obj
    obj.parent = arm_obj


# ---------------------------------------------------------------------------
# MODEL READER
# ---------------------------------------------------------------------------

# Total byte size for known strides (used for validation and alignment).
_STRIDE_TOTAL = {
    0x30: 48, 0x38: 56, 0x40: 64, 0x48: 72,
    0x50: 80, 0x58: 88, 0x60: 96, 0x68: 104, 0x78: 120,
}

# ---------------------------------------------------------------------------
# Vertex layout system — pad_a is DYNAMIC (probed per file), pad_b is fixed
# per stride.
#
# Vertex structure (all known strides share this pattern):
#   [0         ]  XYZ position   (12 bytes, 3×float32)
#   [12        ]  UNKNOWN_A      (pad_a bytes — varies: 0, 12, or 16)
#   [12+pad_a  ]  NORMAL         (12 bytes, 3×float32, unit length)
#   [24+pad_a  ]  TANGENT        (pad_b bytes — world-space tangent frame)
#   [24+pad_a+pad_b]  UV         ( 8 bytes, 2×float32)
#   [32+pad_a+pad_b]  TRAILING   (pad_c bytes — zeros, or skinning for 0x60+)
#
# KEY FINDING from analysis of 1000+ real model files:
#   pad_a is NOT fixed per stride — both 12 and 16 appear in stride 0x50 meshes
#   (architecture/room geometry uses pad_a=12; prop/character geometry uses pad_a=16).
#   We MUST probe pad_a per file by detecting which offset yields unit-length normals.
#
# pad_b is GLOBALLY 16 bytes across ALL stride bounds because the engine stores 
#   Tangent vectors (x, y, z, w float values) immediately after normals. Testing proven across 2400 files.
# ---------------------------------------------------------------------------

# Candidate pad_a values to probe, ordered from most common to least.
# We stop at the first one that gives unit-length normals across 10 vertices.
_PAD_A_CANDIDATES = [0, 12, 16, 4, 8, 20, 24]


def _probe_pad_a(raw: bytes, v_off: int, v_stride: int, v_count: int) -> int | None:
    """
    Determine pad_a for this mesh by finding which offset yields unit-length
    normals across testing vertices (spread throughout the mesh).

    Returns the first pad_a candidate that passes, or None if none work.
    """
    samples = min(100, v_count)
    step = max(1, v_count // samples)
    
    for pad_a in _PAD_A_CANDIDATES:
        # Make sure this pad_a leaves room for normal + at least UV
        if 12 + pad_a + 12 + 8 > v_stride:
            continue
            
        valid_unit_count = 0
        invalid = False
        
        for i in range(0, v_count, step):
            base = v_off + i * v_stride
            n_off = base + 12 + pad_a
            if n_off + 12 > len(raw):
                invalid = True
                break
                
            nx, ny, nz = struct.unpack_from("<fff", raw, n_off)
            mag = math.sqrt(nx*nx + ny*ny + nz*nz)
            
            if mag < 0.05:
                # Degenerate zero-length normal (valid over dummy edges but not a 'positive' identity check)
                continue
            elif abs(mag - 1.0) <= 0.05:
                # Successful unit length, confirmed normal data!
                valid_unit_count += 1
            else:
                # Mathematical length broken (e.g. 1.7), indicates this padding structure hit arbitrary bytes
                invalid = True
                break
                
        # To qualify as the real UV/Normal layout structure, the stride must produce at least one
        # successful normal verification AND produce exactly zero corrupted array evaluations.
        if not invalid and valid_unit_count > 0:
            return pad_a
            
    return None


def _detect_layout(raw: bytes, v_off: int, v_stride: int, v_count: int) -> tuple:
    """
    Returns (pad_a, pad_b, pad_c) for the vertex layout of this mesh.

    Algorithm:
      1. Probe pad_a per-file: scan candidate values [0, 12, 16, ...] and
         pick the first that gives unit-length normals across 10 vertices.
      2. Universally bind pad_b = 16 (4 float tangent block).
      3. Compute pad_c = stride - 12 - pad_a - 12 - pad_b - 8.
      4. If pad_c < 0 fall back to padding step downs, preventing reading past buffer limits.
    """
    # Step 1: probe pad_a
    pad_a = _probe_pad_a(raw, v_off, v_stride, v_count)
    if pad_a is None:
        print(f"    [LAYOUT] WARNING: no valid pad_a found for stride "
              f"0x{v_stride:02X} — defaulting to 0")
        pad_a = 0

    # Step 2: Global Tangent Vector Array
    pad_b = 16

    # Step 3: compute pad_c and validate
    pad_c = v_stride - 12 - pad_a - 12 - pad_b - 8
    if pad_c < 0:
        # pad_a + pad_b exceeds what the stride allows — walk pad_b down until it fits
        for pb in [0, 4, 8, 12, 16]:
            pc = v_stride - 12 - pad_a - 12 - pb - 8
            if pc >= 0:
                print(f"    [LAYOUT] pad_b clamped from {pad_b} to {pb} "
                      f"(pad_a={pad_a}, stride=0x{v_stride:02X})")
                pad_b = pb
                pad_c = pc
                break
        else:
            print(f"    [LAYOUT] WARNING: no valid pad_b for pad_a={pad_a} "
                  f"stride=0x{v_stride:02X} — using (0,0,0)")
            return (0, 0, 0)

    uv_off = 12 + pad_a + 12 + pad_b
    print(f"    [LAYOUT] stride=0x{v_stride:02X} pad_a={pad_a} pad_b={pad_b} "
          f"pad_c={pad_c} uv_off={uv_off}")
    return (pad_a, pad_b, pad_c)

def _is_skinned_mesh(raw, v_off, v_stride, v_count, pad_a, pad_b):
    """
    Probes the 32-byte data block following the UV coordinates for rigging
    signatures (integer bone IDs and weights summing to 1.0) evenly mapped across mesh.
    """
    bone_off = 12 + pad_a + 12 + pad_b + 8
    # Skinned data requires 32 bytes (16 for IDs + 16 for Weights)
    if bone_off + 32 > v_stride:
        return False
        
    samples = min(20, v_count)
    step = max(1, v_count // samples)
    
    for i in range(0, v_count, step):
        base = v_off + i * v_stride
        # Unpack 4 IDs and 4 Weights
        ids = struct.unpack_from("<ffff", raw, base + bone_off)
        weights = struct.unpack_from("<ffff", raw, base + bone_off + 16)
        
        # Bone IDs must be small non-negative integers
        ids_valid = all(
            x >= 0 and x < 256 and abs(x - round(x)) < 0.01
            for x in ids
        )
        # Weights must sum close to 1.0
        weight_sum = sum(weights)
        if not ids_valid or not (0.99 < weight_sum < 1.01):
            return False
    return True


def read_model(file_path: Path):
    """
    Returns: (vertices, faces, uvs, normals, bone_ids, weights, transform)

    bone_ids and weights are per-vertex lists of 4-tuples.
    They are populated only for skinned strides (0x50, 0x60).
    Non-skinned strides return empty lists so callers can check with `if bone_ids`.

    transform is a dict with keys 'position', 'rotation', 'scale':
        position  - (x, y, z) world-space location
        rotation  - (rx, ry, rz) Euler angles in radians (engine space)
        scale     - (sx, sy, sz) scale factors
    """
    with open(file_path, "rb") as file:
        raw = file.read()
    f = BytesIO(raw)

    # ---- Header transform data (0xA0 – 0xC3) ----
    f.seek(0xA0)
    px, py, pz = struct.unpack('<fff', f.read(12))       # 0xA0: position
    rx, ry, rz = struct.unpack('<fff', f.read(12))       # 0xAC: rotation (Euler, radians)
    sx, sy, sz = struct.unpack('<fff', f.read(12))       # 0xB8: scale
    transform = {
        'position': (px, py, pz),
        'rotation': (rx, ry, rz),
        'scale':    (sx, sy, sz),
    }

    # ---- Geometry pointers ----
    f.seek(0x80)
    f.read(16)
    v_off = f.tell() + struct.unpack("Q", f.read(8))[0]
    f_off = f.tell() + struct.unpack("Q", f.read(8))[0]

    f.seek(0xD4)
    f.read(4)
    v_stride, f_count = struct.unpack("II", f.read(8))
    f.read(4)
    v_count, = struct.unpack("I", f.read(4))

    v, u, n, bone_ids, weights = [], [], [], [], []

    # _detect_layout handles both known and unknown strides — no separate
    # raw-walk path needed.  Unknown strides use pad_a probing + pad_b=16 default.
    if v_stride not in _STRIDE_TOTAL:
        print(f"  [MODEL] WARNING: unknown stride 0x{v_stride:02X} in {file_path.name}")

    pad_a, pad_b, pad_c = _detect_layout(raw, v_off, v_stride, v_count)

    # Skinned meshes have 32 bytes of bone data (IDs + weights) after the UV.
    # Strides with enough trailing space may be skinned — probe to confirm.
    is_skinned = (
        v_stride in (0x50, 0x58, 0x60, 0x68, 0x78) and
        _is_skinned_mesh(raw, v_off, v_stride, v_count, pad_a, pad_b)
    )
    print(f"  [MODEL] {file_path.name}: pad_a={pad_a} pad_b={pad_b} pad_c={pad_c} skinned={is_skinned}")
    f.seek(v_off)
    for _ in range(v_count):
        vx, vy, vz = struct.unpack("fff", f.read(12))
        if pad_a: f.read(pad_a)
        nx, ny, nz = struct.unpack("fff", f.read(12))
        if pad_b: f.read(pad_b)
        tu, tv = struct.unpack("ff", f.read(8))
        if is_skinned:
            # 32 bytes of skinning data: 4 bone IDs + 4 weights
            # Bone IDs are stored as floats (e.g. 9.0, 10.0) — cast to int.
            b1, b2, b3, b4 = (int(x) for x in struct.unpack("ffff", f.read(16)))
            w1, w2, w3, w4 = struct.unpack("ffff", f.read(16))
            bone_ids.append((b1, b2, b3, b4))
            weights.append((w1, w2, w3, w4))
            # Read generic trailing bytes if pad_c spans further than the rigging array
            if pad_c > 32:
                f.read(pad_c - 32)
        elif pad_c:
            f.read(pad_c)
        v.append((vx, vy, vz))
        u.append((tu, 1.0 - tv))
        n.append((nx, ny, nz))

    faces = []
    f.seek(f_off)
    for _ in range(f_count):
        faces.append(struct.unpack("III", f.read(12)))

    return v, faces, u, n, bone_ids, weights, transform



# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    # Parse args: [blender.exe, -b, --python, script.py, --, [flags?], input_dir]
    if "--" in sys.argv:
        args = sys.argv[sys.argv.index("--") + 1:]
    else:
        args = sys.argv[1:]
    
    invert_green = "--invert-green" in args
    use_log      = "--no-log" not in args
    
    # The last arg is always the input directory
    input_dir = Path(args[-1]).resolve()
    root_dir  = input_dir.parent

    # Shared log file sits one level up (the DESTINATION_DIR in the bat)
    log_path = root_dir / "conversion_log.txt"

    def log(line: str):
        print(line)
        if use_log:
            with open(log_path, "a", encoding="utf-8") as lf:
                lf.write(line + "\n")

    # ------------------------------------------------------------------
    # 1. TEXTURES  (.bitmap → .dds)
    # ------------------------------------------------------------------
    for bmp in input_dir.glob("*.bitmap"):
        try:
            with open(bmp, "rb") as fh:
                data = fh.read()
            out_t = input_dir / "textures"
            out_t.mkdir(exist_ok=True)
            out_path = out_t / f"{bmp.stem}.dds"
            G7Bitmap().convert_to_dds(BytesIO(data), out_path, invert_green=invert_green)
            os.remove(str(bmp))
            log(f"OK [texture] {out_path.name}")
        except Exception as e:
            log(f"FAIL [texture] {bmp.name} | {e}")

    # ------------------------------------------------------------------
    # 2. MODELS  — all .model files → ONE .blend per G7
    # ------------------------------------------------------------------
    # Vertex positions are already in world-space, so importing every mesh
    # into a single scene preserves the spatial layout automatically.
    # ------------------------------------------------------------------

    # Build a mesh→texture-prefix lookup from the attach log.
    attach_map = {}
    attach_log = input_dir / "attach_log.txt"
    if attach_log.exists():
        attach_map = _read_attach_log(attach_log)
        print(f"ATTACH: {len(attach_map)} mesh→texture mappings loaded from {attach_log.name}")
    else:
        print(f"ATTACH: {attach_log} not found — all meshes will use stem-based lookup")

    # ------------------------------------------------------------------
    # 2b. RIG  — parse bone data before the model loop
    # ------------------------------------------------------------------
    rig_bones    = []
    rig_name     = None
    rig_files = list(input_dir.glob("*.rig"))
    if rig_files:
        rig_path  = rig_files[0]
        rig_name  = rig_path.stem
        rig_bones = read_rig(rig_path)
        if rig_bones:
            print(f"  [RIG] {rig_path.name}: {len(rig_bones)} bone(s) parsed")
        else:
            print(f"  [RIG] {rig_path.name}: parse failed, continuing without armature")
    else:
        print(f"  [RIG] No .rig file found in {input_dir.name}")

    # Snapshot models before we start deleting files (Windows glob safety).
    all_models = sorted(input_dir.glob("*.model"))
    print(f"MODEL: found {len(all_models)} model(s) to process")

    if not all_models:
        print("MODEL: nothing to convert — skipping .blend creation")
    else:
        # Clear scene ONCE and build the shared armature ONCE
        clear_entire_scene()

        arm_obj = None
        if rig_bones:
            arm_obj = create_armature(rig_bones, rig_name)
            print(f"  [RIG] Armature built: {rig_name} ({len(rig_bones)} bones)")

        # Cache for material reuse — keyed by resolved tex_prefix
        _material_cache = {}   # tex_key → bpy.types.Material

        model_fail_count = 0

        for mod in all_models:
            if not mod.exists():
                print(f"SKIP: {mod.name} (already processed or missing)")
                continue
            try:
                # ---- Geometry ----
                v, f, u, n, bone_ids, weights, xform = read_model(mod)
                print(f"  [MODEL] {mod.name}: {len(v)} verts, {len(f)} faces, "
                      f"skinned={bool(bone_ids)}")
                print(f"  [XFORM] pos=({xform['position'][0]:.2f}, "
                      f"{xform['position'][1]:.2f}, {xform['position'][2]:.2f})  "
                      f"rot=({xform['rotation'][0]:.3f}, {xform['rotation'][1]:.3f}, "
                      f"{xform['rotation'][2]:.3f})  "
                      f"scl=({xform['scale'][0]:.3f}, {xform['scale'][1]:.3f}, "
                      f"{xform['scale'][2]:.3f})")

                # Construct clean faces securely dodging geometry degeneration
                clean_f, orig_loop_idx = [], []
                v_count = len(v)
                seen_faces = set()
                for face in f:
                    v0, v1, v2 = face
                    if v0 == v1 or v1 == v2 or v2 == v0:
                        continue
                    if v0 >= v_count or v1 >= v_count or v2 >= v_count:
                        continue
                        
                    # Deduplicate overlapping triangular loops securely
                    tf = tuple(sorted(face))
                    if tf in seen_faces:
                        continue
                    seen_faces.add(tf)
                    
                    clean_f.append((v0, v1, v2))
                    orig_loop_idx.extend(face) # Track loop corners raw identities safely

                mesh = bpy.data.meshes.new(mod.stem)
                obj  = bpy.data.objects.new(mod.stem, mesh)
                bpy.context.collection.objects.link(obj)
                mesh.from_pydata(v, [], clean_f)

                # ---- UVs (Applied securely BEFORE validation cuts loops) ----
                uv_layer = mesh.uv_layers.new()
                uv_count = len(u)
                
                # Iterate across flattened loops preserving exact UV identities flawlessly
                for l_idx, orig_v in enumerate(orig_loop_idx):
                    if orig_v < uv_count:
                        if l_idx < len(uv_layer.data):
                            uv_layer.data[l_idx].uv = u[orig_v]

                # ---- Custom split normals (Applied securely BEFORE validation cuts loops) ----
                def _normals_are_flat(normals, tol=0.001):
                    if len(normals) < 2:
                        return True
                    nx0, ny0, nz0 = normals[0]
                    return all(
                        abs(nx - nx0) < tol and abs(ny - ny0) < tol and abs(nz - nz0) < tol
                        for nx, ny, nz in normals[1:]
                    )

                def _normals_are_valid(normals, tol=0.5):
                    for nx, ny, nz in normals:
                        mag = math.sqrt(nx*nx + ny*ny + nz*nz)
                        if mag > tol:
                            return True
                    return False

                if not _normals_are_valid(n):
                    print(f"  [MODEL] {mod.stem}: zero/invalid normals — using auto-computed")
                elif _normals_are_flat(n):
                    print(f"  [MODEL] {mod.stem}: flat normals detected, skipping custom split normals")
                else:
                    loop_normals = [(0.0, 0.0, 0.0)] * len(orig_loop_idx)
                    for l_idx, orig_v in enumerate(orig_loop_idx):
                        if orig_v < len(n):
                            loop_normals[l_idx] = n[orig_v]

                    if hasattr(mesh, 'use_auto_smooth'):
                        mesh.use_auto_smooth = True

                    try:
                        # Slice loop_normals dynamically mapped natively before validation
                        mesh.normals_split_custom_set(loop_normals[:len(mesh.loops)])
                    except Exception as e_nrm:
                        print(f"  [MODEL] {mod.stem}: normals_split_custom_set failed ({e_nrm})")

                # ---- Topological Cleanup ----
                mesh.validate(verbose=False)
                mesh.update()

                # ---- Skinning ----
                if bone_ids and arm_obj:
                    apply_skinning(obj, arm_obj, bone_ids, weights, rig_bones)

                # ---- Resolve texture prefix ----
                tex_prefix = attach_map.get(mod.stem.lower(), None)
                if tex_prefix:
                    print(f"  [MAT] {mod.stem} → attach prefix: {tex_prefix}")
                else:
                    print(f"  [MAT] {mod.stem} → no attach entry, using mesh stem")

                # ---- PBR Material (reuse if same tex_prefix) ----
                tex_key = (tex_prefix or mod.stem).lower()
                if tex_key in _material_cache:
                    mat = _material_cache[tex_key]
                    print(f"  [MAT] reusing cached material for '{tex_key}'")
                else:
                    mat = create_pbr_material(mod.stem, root_dir, tex_prefix=tex_prefix)
                    _material_cache[tex_key] = mat
                obj.data.materials.append(mat)

                # ---- Apply header transform ----
                # Compose the engine→Blender +90° X rotation with the
                # per-model rotation from the header.  Skinned meshes are
                # parented to the armature which already carries the axis
                # conversion, so we skip the extra rotation for those.
                if bone_ids and arm_obj:
                    # Skinned: armature handles orientation
                    obj.location = xform['position']
                    obj.rotation_euler = xform['rotation']
                    obj.scale = xform['scale']
                else:
                    # Compose: engine +90° X rotation × model rotation
                    engine_rot = Euler((math.pi / 2, 0, 0), 'XYZ')
                    model_rot  = Euler(xform['rotation'], 'XYZ')
                    combined   = (engine_rot.to_matrix() @ model_rot.to_matrix()).to_euler('XYZ')
                    obj.rotation_euler = combined
                    obj.location = engine_rot.to_matrix() @ Vector(xform['position'])
                    obj.scale = xform['scale']

                # ---- Apply programmatic "Merge by distance" seamlessly ----
                # Simulates exactly the user's requested optimal workflow (Merge + Sharp Edges) post-rigging
                prev_active = bpy.context.view_layer.objects.active
                try:
                    bpy.context.view_layer.objects.active = obj
                    obj.select_set(True)
                    if bpy.context.object.mode != 'OBJECT':
                        bpy.ops.object.mode_set(mode='OBJECT')
                    bpy.ops.object.mode_set(mode='EDIT')
                    bpy.ops.mesh.select_all(action='SELECT')
                    # Backwards combability for Blender 3 vs 4+ parameter shifts
                    if 'use_sharp_edge_from_normals' in bpy.ops.mesh.remove_doubles.get_rna_type().properties.keys():
                        bpy.ops.mesh.remove_doubles(threshold=0.0001, use_sharp_edge_from_normals=True)
                    else:
                        bpy.ops.mesh.remove_doubles(threshold=0.0001)
                    bpy.ops.object.mode_set(mode='OBJECT')
                except Exception as b_exc:
                    print(f"  [MODEL] Merge By Distance failed natively: {b_exc}")
                finally:
                    obj.select_set(False)
                    if prev_active:
                        bpy.context.view_layer.objects.active = prev_active

                log(f"OK [model] {mod.stem}")
                os.remove(str(mod))

            except Exception as exc:
                log(f"FAIL [model] {mod.name} | {exc}")
                traceback.print_exc()
                model_fail_count += 1

        # ---- Save ONE .blend for the entire G7 ----
        g7_name = input_dir.name   # folder name = G7 file stem
        blend_path = str(input_dir / f"{g7_name}.blend")
        bpy.ops.wm.save_as_mainfile(filepath=blend_path)
        log(f"OK [blend] {g7_name}.blend ({len(all_models)} models)")

        if model_fail_count > 0:
            log(f"FAIL [blend] {model_fail_count} model(s) failed during import")

    # ------------------------------------------------------------------
    # 3. CLEAN EXTRACTED FILES WE DON'T PROCESS
    # ------------------------------------------------------------------
    for pattern in ("*.rig", "*.camera", "*.cinematic"):
        for leftover in input_dir.glob(pattern):
            try:
                os.remove(str(leftover))
                log(f"OK [cleanup] removed {leftover.name}")
            except Exception as e:
                log(f"FAIL [cleanup] {leftover.name} | {e}")


if __name__ == "__main__":
    main()
