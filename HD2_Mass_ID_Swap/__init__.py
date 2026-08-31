bl_info = {
    "name": "HD2_Mass_ID_Swap",
    "author": "HD2SDK Script Workspace",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > HD2",
    "description": "Collect source armor Units and destination archives for multi-ID swaps",
    "category": "Import-Export",
}

import copy
import base64
import hashlib
import importlib
import json
import os
import struct
import sys
import zlib

import bpy
import bpy.utils.previews
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, IntProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup, UIList


MAX_COVER_CANDIDATES = 50000
MAX_SOLVER_STATES = 250000
SUPPORT_ICONS = None
ARMOR_LIST_CACHE = {}
# These TOCs are intentionally separate from HD2SDK's TocManager.  Loading an
# archive through TocManager makes it appear in the SDK's "Loaded Archives"
# UI, which is undesirable for a read-only destination lookup.
TRANSIENT_ARCHIVES = {}
TRANSIENT_UNIT_ENTRIES = {}
HIDDEN_SOURCE_CACHE = {}
EMBEDDED_SUPPORT_ICONS = {
    "paypal": "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAACcElEQVR42m2SS0jUURSHv3Pvf2Z0NB8VihGaKWGWRe0iclYVQpsC3RREFLqLFpGbYJhFgUgLd0W0iSCaoo1B0UZdVUQUkUKGCkH2GBojbcYZ597TYpx85G91uXC+e853rrA68bghkfDsHYhhoqdxWQcYMIuoe8lE/31QAdFSSbAGMIoBPF7OECq/AB7EgiqY0EU6Blt4zzV6kpaHPY4ifVXG8ACI7sBlHPn5PIvfHYupPPm0spQ9gYjycPxfB6sBAglPLB4AO0Et+XRA9oel8DNE6qPStq2Dp0vHIeFJql0HiAsAs6F6kAb8EhTyggcyOcEGjs7OKKl0FwDjyDoHE0VAOGjChMpxOU9l1CCqVG5yxA47mhpDfP/yoSRsLSDWLowB1rRSEKir9XSfEkwg1G4NiEQDUl8mKDePUBXAkVgvEQC7C6eezdWemhowJs3879v8/HYFzcY41/yraKy4ypUO6vYsm/UHkLChqkIJlzv8wgh923tXHlApFZckCrF4wPRc8WxtnMKfY7Q3v6OqMsDaKYYmIyS1smh+uVhViOsGE5RyZzbGg9xZhiZb1twn1RIfCVZ233Z9C8ZcwtgMkYUh3iQy/8FuTZ+ltqGFudlh+lpeA3D7cyvqOgICewSVTpQaFqPCnhsZKHwlsDmqNr1iYSGGCc6QmS8gwUFuzTxGxOJdIyJiwOzGloXB3wO6QOpQOYdzh0iln1FT3UrY1pPLjKNaQMx+kJOIHMXwwuC9Zyl7lfH+QVRGseFq8HcxZoaCn2L4/B2yuSf07biM6k0iFWWovkX1Od59WpmzO2mXv3TRbPtAL/sG69bI2yB/AR6y8SXyg7NRAAAAAElFTkSuQmCC",
    "kofi": "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAACSElEQVR42qWTT0tUcRSGn/O7d+6d8Ro6Uu3cZYlUqCAmQYkbK3KpVvYBWvQBohZJi7YFRos+gP9aCCVYG4M2LYxSMxEtCApaVOrkaHPv3Ps7LUZzdGrVWR7OX97nhfJQFVQN/wpVg6qUp9w9zSIKaONU2CqOnMPao6Uqs6xFfbYk8mZfLVKeaBpfr5Oa9AMc97JJO6DbwwVsIYEkHtFc4fpiX+3qTo9w+7aBQU60URO74TTVfnO8vmUBu+8B42erDJvhrER+17sZcjCI9I6r87hPksbJ/KiTDfqr8luRg3r6Z7uAMYCyFtrI1gSet7E5tnih+lLvuDoC0PY83/xN02/PZpPkXnPKEU8w2/8poEVFEHJF5cZ8lLz66ToHKbTMdFfPugChNT027eihVKRZz6P4Yhq+fC5dUF9PqrOLu+8j6nzDUEtKz7w2msvRA5QGqGgDisQqKJCfmMAuzJceP36S2s4uFnKWBOXaEZeMICHSAPBXzdMDA0gQIEFAMHAVVbjfkmK4w+fhhyLfI0hLGQeiuoKgKUcQlEz7Kfybt0oXtLcDyssfMPypwNx6QnU2pfGWruwOMDx1o+TOch75WoCMWEzHaQBsaPmlwqOPRebWLIczRmwhEcdJPQF2ZWyazI/a2qA/s7EV+a54aks6ijGEVtmMwRMbSW3gFVc3x5Yu7shYBpJ1w2k94DcX1/aCJIBrMKamyiQb4awbl4FUgXK2aggxV/ajnBQSNIlHpALlSjPROBW2Gtfp1iQ+tsdM5/0KM/G/dv4N4zQouRknkjEAAAAASUVORK5CYII=",
}


class MappingError(Exception):
    """Raised when a globally consistent ID-swap mapping cannot be made."""


def is_sdk_module(module):
    return module is not None and all(
        hasattr(module, attribute)
        for attribute in ("Global_TocManager", "UnitID", "GetFriendlyNameFromID")
    )


def get_sdk():
    """Find the active HD2SDK addon, including the official ZIP's module name."""
    for module_name in ("HD2SDK", "HD2SDK-CommunityEdition"):
        module = sys.modules.get(module_name)
        if is_sdk_module(module):
            return module
        try:
            module = importlib.import_module(module_name)
        except (ImportError, ValueError):
            continue
        if is_sdk_module(module):
            return module

    try:
        import addon_utils
        for module in addon_utils.modules():
            if is_sdk_module(module):
                return module
            if getattr(module, "bl_info", {}).get("name") == "Helldivers 2 SDK: Community Edition":
                active_module = importlib.import_module(module.__name__)
                if is_sdk_module(active_module):
                    return active_module
    except (ImportError, AttributeError, ValueError):
        pass
    return None


def write_support_icon(path, kind):
    """Create small local PNG previews without depending on an internet connection."""
    size = 64
    background = (0, 48, 135, 255) if kind == "paypal" else (41, 171, 224, 255)
    pixels = [[background for _ in range(size)] for _ in range(size)]

    def rect(left, top, width, height, color):
        for y in range(max(0, top), min(size, top + height)):
            for x in range(max(0, left), min(size, left + width)):
                pixels[y][x] = color

    white = (255, 255, 255, 255)
    if kind == "paypal":
        # A compact, high-contrast P mark in the familiar PayPal blue palette.
        rect(19, 13, 9, 38, white)
        rect(27, 13, 18, 8, white)
        rect(37, 20, 8, 11, white)
        rect(27, 31, 18, 8, white)
        rect(25, 24, 15, 7, (0, 156, 222, 255))
    else:
        # White coffee cup plus the characteristic warm heart accent.
        rect(14, 23, 29, 5, white)
        rect(17, 28, 23, 16, white)
        rect(23, 44, 13, 4, white)
        rect(43, 28, 7, 12, white)
        rect(46, 30, 4, 8, background)
        heart = (255, 95, 126, 255)
        rect(24, 31, 5, 5, heart)
        rect(31, 31, 5, 5, heart)
        rect(26, 36, 8, 5, heart)
        rect(28, 41, 4, 3, heart)

    raw = bytearray()
    for row in pixels:
        raw.append(0)  # PNG filter: none
        for pixel in row:
            raw.extend(pixel)

    def chunk(name, payload):
        return struct.pack(">I", len(payload)) + name + payload + struct.pack(">I", zlib.crc32(name + payload) & 0xffffffff)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as icon_file:
        icon_file.write(png)


def support_icon_value(name):
    if SUPPORT_ICONS is None or name not in SUPPORT_ICONS:
        return 0
    return SUPPORT_ICONS[name].icon_id


def entry_label(sdk, entry_id):
    try:
        friendly_name = sdk.GetFriendlyNameFromID(int(entry_id))
    except Exception:
        friendly_name = str(entry_id)
    return str(entry_id) if friendly_name == str(entry_id) else f"{friendly_name} ({entry_id})"


def contains_source(items, entry_id, type_id):
    return any(item.entry_id == str(entry_id) and item.type_id == str(type_id) for item in items)


def contains_destination(items, archive_id):
    return any(item.archive_id == str(archive_id) for item in items)


def active_sources(scene):
    return scene.hd2_ms_helmet_sources if scene.hd2_ms_mode == "HELMET" else scene.hd2_ms_sources


def active_destinations(scene):
    return scene.hd2_ms_helmet_destinations if scene.hd2_ms_mode == "HELMET" else scene.hd2_ms_destinations


def active_source_index_property(scene):
    return "hd2_ms_helmet_source_index" if scene.hd2_ms_mode == "HELMET" else "hd2_ms_source_index"


def active_destination_index_property(scene):
    return "hd2_ms_helmet_destination_index" if scene.hd2_ms_mode == "HELMET" else "hd2_ms_destination_index"


def active_dataset_mode(scene):
    return "HELMET" if scene.hd2_ms_mode == "HELMET" else "ARMOR"


def is_unknown_helmet(scene, archive_name):
    return scene.hd2_ms_mode == "HELMET" and str(archive_name).strip().casefold() == "unknown helmet"


def add_source_units(sdk, scene, entry_ids):
    unit_id = int(sdk.UnitID)
    added = 0
    for entry_id in dict.fromkeys(int(entry_id) for entry_id in entry_ids):
        entry = sdk.Global_TocManager.GetEntry(entry_id, unit_id)
        sources = active_sources(scene)
        if entry is None or contains_source(sources, entry_id, unit_id):
            continue
        item = sources.add()
        item.entry_id = str(entry_id)
        item.type_id = str(unit_id)
        item.label = entry_label(sdk, entry_id)
        added += 1
    return added


def clear_transient_archives():
    """Release addon-only TOCs after a mapping run; never touch HD2SDK state."""
    TRANSIENT_ARCHIVES.clear()
    TRANSIENT_UNIT_ENTRIES.clear()


def archive_read_path(sdk, archive_id):
    """Resolve an archive path from the SDK search index without loading it."""
    archive_id = str(archive_id).lower()
    for archive in sdk.Global_TocManager.SearchArchives:
        if (
            str(archive.Name).lower() == archive_id
            or os.path.basename(str(archive.Path)).lower() == archive_id
        ):
            return str(archive.Path)
    return os.path.join(sdk.Global_gamepath, archive_id)


def get_transient_archive(sdk, archive_id):
    """Read a TOC privately, without calling ``TocManager.LoadArchive``."""
    path = archive_read_path(sdk, archive_id)
    cache_key = os.path.normcase(os.path.abspath(path))
    cached = TRANSIENT_ARCHIVES.get(cache_key)
    if cached is not None:
        return cached
    try:
        archive = sdk.StreamToc()
        if not archive.FromFile(path, SerializeData=False):
            raise MappingError(f"Could not read archive TOC: {archive_id}")
    except MappingError:
        raise
    except Exception as error:
        raise MappingError(f"Could not read archive TOC {archive_id}: {error}") from error

    # BodyType and rig checks need only the Unit's TOC bytes, not GPU/stream
    # payloads. Hydrate those bytes directly from this private TOC.
    for entry_id, entry in archive.TocDict.get(int(sdk.UnitID), {}).items():
        start = int(entry.TocDataOffset)
        end = start + int(entry.TocDataSize)
        entry.TocData = bytearray(archive.TocFile.Data[start:end])
        TRANSIENT_UNIT_ENTRIES.setdefault(int(entry_id), entry)
    TRANSIENT_ARCHIVES[cache_key] = archive
    return archive


def get_destination_unit_ids(sdk, archive_id):
    """Return destination IDs from HD2SDK's lightweight search TOCs when possible."""
    archive_id = str(archive_id).lower()
    unit_id = int(sdk.UnitID)
    for archive in sdk.Global_TocManager.SearchArchives:
        if (
            str(archive.Name).lower() == archive_id
            or os.path.basename(str(archive.Path)).lower() == archive_id
        ):
            return list(dict.fromkeys(int(entry_id) for entry_id in archive.TocEntries.get(unit_id, [])))

    # This fallback is needed only when HD2SDK has not built SearchArchives
    # yet. It is deliberately private, so it does not add to Loaded Archives.
    archive = get_transient_archive(sdk, archive_id)
    return list(archive.TocDict.get(unit_id, {}).keys())


def get_transient_unit_entry(target_id):
    entry = TRANSIENT_UNIT_ENTRIES.get(int(target_id))
    if entry is None:
        raise MappingError(f"Could not read destination Unit {target_id} from the selected archive TOCs.")
    return entry


def payload_digest(entry):
    """Content-address a complete resource, not merely its source ID."""
    toc_data = bytes(entry.TocData)
    gpu_data = bytes(entry.GpuData)
    stream_data = bytes(entry.StreamData)
    digest = hashlib.sha256()
    for data in (toc_data, gpu_data, stream_data):
        digest.update(len(data).to_bytes(8, "little"))
        digest.update(data)
    return digest.digest(), (toc_data, gpu_data, stream_data)


def normalize_body_type(value):
    value = str(value or "").strip()
    prefix = "HelldiverCustomizationBodyType_"
    if value.startswith(prefix):
        value = value[len(prefix):]
    aliases = {
        "lean": "Slim",
        "slim": "Slim",
        "brawny": "Stocky",
        "stocky": "Stocky",
        "any": "Any",
    }
    return aliases.get(value.lower(), value)


def entry_body_type(entry):
    """Read the SDK's CustomizationInfo BodyType without rebuilding geometry."""
    data = bytes(entry.TocData)
    # StingrayMeshFile writes CustomizationInfoOffset at byte 76. The
    # CustomizationInfo reader then skips 24 bytes before its first string.
    if len(data) < 80:
        raise MappingError(f"Unit {entry.FileID} has no readable customization metadata.")
    customization_offset = struct.unpack_from("<I", data, 76)[0]
    if customization_offset == 0 or customization_offset + 28 > len(data):
        raise MappingError(f"Unit {entry.FileID} has no readable BodyType.")
    string_length = struct.unpack_from("<I", data, customization_offset + 24)[0]
    string_start = customization_offset + 28
    string_end = string_start + string_length
    if string_length == 0 or string_end > len(data):
        raise MappingError(f"Unit {entry.FileID} has an invalid BodyType string.")
    body_type = bytes(data[string_start:string_end]).replace(b"\x00", b"").decode("utf-8", "replace")
    body_type = normalize_body_type(body_type)
    if not body_type:
        raise MappingError(f"Unit {entry.FileID} has an empty BodyType.")
    return body_type


def optional_entry_body_type(entry):
    """Return BodyType when present; some valid Units only have slot JSON metadata."""
    try:
        return entry_body_type(entry)
    except MappingError:
        return None


def is_hidden_dummy_unit(entry):
    """Recognize the valid one-vertex/zero-index Units commonly used to hide geometry."""
    cache_key = (
        int(getattr(entry, "TocDataOffset", 0)),
        int(getattr(entry, "GpuResourceOffset", 0)),
        int(getattr(entry, "StreamOffset", 0)),
        len(getattr(entry, "TocData", b"")),
        len(getattr(entry, "GpuData", b"")),
        len(getattr(entry, "StreamData", b"")),
    )
    # Fresh in-memory SDK entries can all have zero offsets; do not cache them
    # together because they may contain different data.
    can_cache = any(cache_key[:3])
    if can_cache and cache_key in HIDDEN_SOURCE_CACHE:
        return HIDDEN_SOURCE_CACHE[cache_key]

    # A hidden Unit may retain several mesh/LOD records, making it larger than
    # the old 4 KB shortcut.  64 KB still avoids parsing normal armor meshes.
    if len(getattr(entry, "GpuData", b"")) > 65536:
        if can_cache:
            HIDDEN_SOURCE_CACHE[cache_key] = False
        return False
    try:
        if not entry.IsLoaded:
            entry.Load(True, False)
        meshes = entry.LoadedData.RawMeshes
        fully_hidden = bool(meshes) and all(
            len(mesh.VertexPositions) == 1
            and not mesh.Indices
            and all(material.NumIndices == 0 for material in mesh.Materials)
            for mesh in meshes
        )
        visible_meshes = [
            mesh for mesh in meshes
            if mesh.Indices or any(material.NumIndices for material in mesh.Materials)
        ]
        visible_vertices = sum(len(mesh.VertexPositions) for mesh in visible_meshes)
        visible_indices = sum(len(mesh.Indices) for mesh in visible_meshes)
        hidden_meshes = len(meshes) - len(visible_meshes)
        # Some existing hide Units keep one tiny sentinel triangle mesh while
        # all LOD/body meshes are one-vertex shells.  Treat that pattern as
        # hidden too; a real armor piece has substantially more geometry.
        mostly_hidden = (
            len(meshes) >= 3
            and hidden_meshes >= len(meshes) - 1
            and len(visible_meshes) <= 1
            and visible_vertices <= 64
            and visible_indices <= 96
        )
        result = fully_hidden or mostly_hidden
        if can_cache:
            HIDDEN_SOURCE_CACHE[cache_key] = result
        return result
    except Exception:
        # A source that cannot be inspected must remain available rather than
        # being incorrectly discarded.
        return False


JSON_BODY_TYPES = {
    "lean": "Slim",
    "brawny": "Stocky",
    "any_shared": "Any",
}


def armor_list_path(mode="ARMOR"):
    """Find the selected mode's class/slot database after ZIP installation."""
    addon_folder = os.path.dirname(os.path.abspath(__file__))
    filename = "Helmet.json" if mode == "HELMET" else "Armor_List.json"
    candidates = (
        os.path.join(addon_folder, filename),
        os.path.join(os.path.dirname(addon_folder), filename),
    )
    return next((path for path in candidates if os.path.isfile(path)), None)


def load_armor_list(mode="ARMOR"):
    """Return the selected mode's archive map plus light/medium/heavy groups."""
    global ARMOR_LIST_CACHE
    path = armor_list_path(mode)
    if path is None:
        raise MappingError(
            f"{'Helmet.json' if mode == 'HELMET' else 'Armor_List.json'} is missing. Reinstall the complete ID-Swap ZIP."
        )
    modified_time = os.path.getmtime(path)
    cached = ARMOR_LIST_CACHE.get(mode)
    if cached is not None and cached[0] == path and cached[1] == modified_time:
        return cached[2], cached[3]
    try:
        with open(path, "r", encoding="utf-8") as details_file:
            raw_details = json.load(details_file)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise MappingError(f"Could not read Armor_List.json: {error}") from error

    archives = {}
    categories = {}
    for category in ("light", "medium", "heavy"):
        category_archives = raw_details.get(category)
        if not isinstance(category_archives, dict):
            raise MappingError(f"Armor_List.json has no valid '{category}' archive group.")
        categories[category] = []
        for archive_id, archive_details in category_archives.items():
            archive_id = str(archive_id).lower()
            if archive_id in archives:
                raise MappingError(f"Armor_List.json repeats archive {archive_id}.")
            if not isinstance(archive_details, dict):
                raise MappingError(f"Armor_List.json has invalid data for archive {archive_id}.")
            archives[archive_id] = archive_details
            categories[category].append((archive_id, str(archive_details.get("name") or archive_id)))
    ARMOR_LIST_CACHE[mode] = (path, modified_time, archives, categories)
    return archives, categories


def semantic_slot_key(group, slot, layer):
    try:
        body_type = JSON_BODY_TYPES[group]
    except KeyError as error:
        raise MappingError(f"Unknown body group '{group}' in Armor_List.json.") from error
    return body_type, str(slot), str(layer)


def canonicalize_shared_slot_keys(slot_targets, entry_id, key, archive_name):
    """Merge one global Unit used by both Slim and Stocky into its Any slot."""
    previous = slot_targets.get(entry_id)
    if previous is None:
        slot_targets[entry_id] = key
        return
    if previous == key:
        return
    if previous[1:] == key[1:] and {previous[0], key[0]}.issubset({"Slim", "Stocky", "Any"}):
        slot_targets[entry_id] = ("Any", previous[1], previous[2])
        return
    raise MappingError(
        f"JSON assigns Unit {entry_id} to incompatible semantic slots in {archive_name}."
    )


def archive_slot_targets(details, archive_id, target_ids):
    """Return a target ID -> (BodyType, slot, layer) map from the JSON database."""
    archive_id = str(archive_id).lower()
    archive_details = details.get(archive_id)
    if not isinstance(archive_details, dict):
        raise MappingError(
            f"Destination archive {archive_id} is not present in Armor_List.json."
        )

    slot_targets = {}
    for group, slots in archive_details.items():
        if group == "name":
            continue
        if not isinstance(slots, dict):
            raise MappingError(f"Invalid slot data for {archive_details.get('name', archive_id)}.")
        for slot, layers in slots.items():
            for layer, entry_ids in layers.items():
                key = semantic_slot_key(group, slot, layer)
                for entry_id in entry_ids:
                    entry_id = int(entry_id)
                    canonicalize_shared_slot_keys(
                        slot_targets,
                        entry_id,
                        key,
                        archive_details.get('name', archive_id),
                    )

    target_ids = {int(target_id) for target_id in target_ids}
    missing = sorted(target_ids - set(slot_targets))
    if missing:
        sample = ", ".join(str(entry_id) for entry_id in missing[:3])
        raise MappingError(
            f"JSON has no slot metadata for {len(missing)} Unit ID(s) in "
            f"{archive_details.get('name', archive_id)} (for example: {sample})."
        )
    # The database may contain entries that no longer exist in this game build;
    # those are ignored. Missing *live* IDs above are never ignored.
    return {entry_id: slot_targets[entry_id] for entry_id in target_ids}


def source_slot_keys(details, source_entries, source_body_types):
    """Resolve each selected source Unit to exactly one JSON semantic slot."""
    reverse_index = {}
    for archive_details in details.values():
        if not isinstance(archive_details, dict):
            continue
        archive_slots = {}
        for group, slots in archive_details.items():
            if group == "name":
                continue
            for slot, layers in slots.items():
                for layer, entry_ids in layers.items():
                    key = semantic_slot_key(group, slot, layer)
                    for entry_id in entry_ids:
                        canonicalize_shared_slot_keys(
                            archive_slots,
                            int(entry_id),
                            key,
                            archive_details.get("name", "unknown archive"),
                        )
        for entry_id, key in archive_slots.items():
            reverse_index.setdefault(entry_id, set()).add(key)

    keys = []
    used_keys = {}
    for source_index, (entry, body_type) in enumerate(zip(source_entries, source_body_types)):
        entry_id = int(entry.FileID)
        candidates = set(reverse_index.get(entry_id, set()))
        if body_type is not None:
            # "Any" represents a global Unit which the armor list assigns to
            # both Slim and Stocky for the same slot/layer.
            candidates = {
                key for key in candidates
                if key[0] == body_type or key[0] == "Any"
            }
        if len(candidates) != 1:
            rendered = ", ".join("/".join(key) for key in sorted(candidates)) or "none"
            body_label = body_type if body_type is not None else "unavailable"
            raise MappingError(
                f"Source Unit {entry_id} cannot be resolved to one slot for BodyType {body_label} "
                f"(JSON candidates: {rendered})."
            )
        key = candidates.pop()
        if key in used_keys:
            raise MappingError(
                f"Source Units {used_keys[key]} and {entry_id} both occupy slot "
                f"{key[0]}/{key[1]}/{key[2]}. Select only one source per slot."
            )
        used_keys[key] = entry_id
        keys.append(key)
    return keys


def solve_slot_assignment(archive_targets, source_keys, destination_slot_targets, allow_cross_body_fallback=False):
    """Prefer semantic slots, then use otherwise-unused source Units as fallback."""
    source_by_key = {key: source_index for source_index, key in enumerate(source_keys)}
    source_by_slot = {}
    for source_index, key in enumerate(source_keys):
        source_by_slot.setdefault(key[1:], []).append(source_index)

    # Work with semantic target keys first. A fallback is assigned once per
    # missing key, so every selected archive receives the same safe mapping.
    target_keys = set()
    for destination, target_ids in archive_targets:
        slot_targets = destination_slot_targets[str(destination.archive_id).lower()]
        target_keys.update(slot_targets[int(target_id)] for target_id in target_ids)

    action_by_key = {}
    used_source_indices = set()
    for key in sorted(target_keys):
        if key in source_by_key:
            action_by_key[key] = ("source", source_by_key[key])
            used_source_indices.add(source_by_key[key])
        elif allow_cross_body_fallback and len(source_by_slot.get(key[1:], [])) == 1:
            source_index = source_by_slot[key[1:]][0]
            action_by_key[key] = ("cross_body_source", source_index)
            used_source_indices.add(source_index)

    # ID swap does not require the source and destination IDs to describe the
    # same body part. When a desired slot is absent, consume an unused source
    # Unit rather than silently preserving the base-game target mesh.
    unmatched_keys = sorted(target_keys - set(action_by_key))
    spare_source_indices = [
        index for index in range(len(source_keys)) if index not in used_source_indices
    ]
    for key, source_index in zip(unmatched_keys, spare_source_indices):
        action_by_key[key] = ("spare_source", source_index)
        used_source_indices.add(source_index)
    for key in unmatched_keys[len(spare_source_indices):]:
        # A valid one-vertex, zero-index mesh hides destination parts for
        # which there are no source Units left to assign.
        action_by_key[key] = ("dummy", None)

    assignment = {}
    cross_body_target_count = 0

    for destination, target_ids in archive_targets:
        slot_targets = destination_slot_targets[str(destination.archive_id).lower()]
        for target_id in target_ids:
            key = slot_targets[int(target_id)]
            action = action_by_key.get(key)
            if action is None:
                raise MappingError(f"Could not resolve a replacement action for {key}.")
            is_new_target = int(target_id) not in assignment
            previous = assignment.setdefault(int(target_id), action)
            if previous != action:
                raise MappingError(
                    f"Global Unit ID {target_id} is requested as incompatible slots across selected destinations."
                )
            if action[0] == "cross_body_source" and is_new_target:
                cross_body_target_count += 1

    unused_sources = sorted(set(range(len(source_keys))) - used_source_indices)

    return {
        "assignment": assignment,
        "source_slot_keys": source_keys,
        "skipped_source_keys": [source_keys[index] for index in unused_sources],
        "target_count": len(assignment),
        "override_target_ids": {
            target_id for target_id, action in assignment.items() if action[0] != "preserve"
        },
        "cross_body_target_count": cross_body_target_count,
        "missing_source_keys": [],
        "spare_source_target_key_count": sum(
            action[0] == "spare_source" for action in action_by_key.values()
        ),
        "dummy_target_count": sum(action[0] == "dummy" for action in assignment.values()),
    }


def format_slot_keys(slot_keys, limit=8):
    rendered = ["/".join(key) for key in slot_keys]
    if len(rendered) > limit:
        return ", ".join(rendered[:limit]) + f", and {len(rendered) - limit} more"
    return ", ".join(rendered)


def popcount(value):
    return value.bit_count()


def unique_destination_sets(archive_targets):
    """Collapse identical Unit sets; they impose the same mapping constraint."""
    unique_sets = []
    for _, target_ids in archive_targets:
        target_set = frozenset(target_ids)
        if target_set not in unique_sets:
            unique_sets.append(target_set)
    return unique_sets


def enumerate_source_covers(ids, id_masks, archive_count):
    """Find all minimal ID groups that occur exactly once in every archive.

    A group is later assigned to one source payload. IDs in one group must not
    share an archive membership, otherwise that source would render twice in
    that destination.
    """
    full_mask = (1 << archive_count) - 1
    ids_by_archive = [
        [index for index, membership in enumerate(id_masks) if membership & (1 << archive_index)]
        for archive_index in range(archive_count)
    ]
    covers = []
    seen = set()

    def visit(covered_archives, selected):
        if len(covers) >= MAX_COVER_CANDIDATES:
            raise MappingError(
                "Mapping has too many possible cover groups. Reduce the destination list and analyze again."
            )
        if covered_archives == full_mask:
            selected_mask = 0
            for index in selected:
                selected_mask |= 1 << index
            if selected_mask not in seen:
                seen.add(selected_mask)
                covers.append(tuple(selected))
            return

        missing_archives = [
            archive_index
            for archive_index in range(archive_count)
            if not (covered_archives & (1 << archive_index))
        ]
        # Branch on the archive with the fewest compatible IDs first.
        archive_index = min(
            missing_archives,
            key=lambda candidate: sum(
                1 for index in ids_by_archive[candidate]
                if not (id_masks[index] & covered_archives)
            ),
        )
        candidates = [
            index for index in ids_by_archive[archive_index]
            if not (id_masks[index] & covered_archives)
        ]
        candidates.sort(key=lambda index: (-popcount(id_masks[index]), ids[index]))
        for index in candidates:
            visit(covered_archives | id_masks[index], selected + (index,))

    visit(0, ())
    return covers, ids_by_archive


def solve_global_assignment(archive_targets, source_count):
    """Return target-ID -> source-index/None using exact archive coverage.

    ``None`` represents the one shared invisible dummy. Every selected archive
    receives every source exactly once, independent of its TOC order.
    """
    archive_sets = unique_destination_sets(archive_targets)
    if not archive_sets:
        raise MappingError("No destination Unit sets were found.")
    if source_count <= 0:
        raise MappingError("At least one source Unit is required.")

    smallest_archive = min(len(target_set) for target_set in archive_sets)
    if source_count > smallest_archive:
        raise MappingError(
            f"{source_count} source Units cannot fit in the smallest destination set ({smallest_archive} Unit IDs)."
        )

    ids = sorted(set().union(*archive_sets))
    archive_count = len(archive_sets)
    id_masks = []
    for target_id in ids:
        membership = 0
        for archive_index, target_set in enumerate(archive_sets):
            if target_id in target_set:
                membership |= 1 << archive_index
        id_masks.append(membership)

    covers, ids_by_archive = enumerate_source_covers(ids, id_masks, archive_count)
    # Source labels are interchangeable while solving. Sorting and requiring
    # increasing cover indices eliminates N! equivalent source permutations.
    covers.sort()
    cover_masks = []
    for cover in covers:
        cover_mask = 0
        for index in cover:
            cover_mask |= 1 << index
        cover_masks.append(cover_mask)

    all_ids_mask = (1 << len(ids)) - 1
    failed_states = set()
    state_count = 0
    limit_reached = False

    def search(used_ids_mask, source_index, minimum_cover_index):
        nonlocal state_count, limit_reached
        state_count += 1
        if state_count > MAX_SOLVER_STATES:
            limit_reached = True
            return None
        if source_index == source_count:
            return []

        remaining_sources = source_count - source_index
        available_ids_mask = all_ids_mask ^ used_ids_mask
        for archive_index in range(archive_count):
            remaining_ids = sum(
                1 for index in ids_by_archive[archive_index]
                if available_ids_mask & (1 << index)
            )
            if remaining_ids < remaining_sources:
                return None

        state_key = (used_ids_mask, source_index, minimum_cover_index)
        if state_key in failed_states:
            return None
        for cover_index in range(minimum_cover_index, len(cover_masks)):
            cover_mask = cover_masks[cover_index]
            if cover_mask & used_ids_mask:
                continue
            result = search(used_ids_mask | cover_mask, source_index + 1, cover_index + 1)
            if result is not None:
                return [cover_masks[cover_index]] + result
        failed_states.add(state_key)
        return None

    selected_covers = search(0, 0, 0)
    if selected_covers is None:
        if limit_reached:
            raise MappingError(
                "Mapping search exceeded its safe complexity limit. Reduce the destination list and analyze again."
            )
        raise MappingError(
            "No global mapping can place every source exactly once in every selected destination archive."
        )

    assignment = {}
    for source_index, cover_mask in enumerate(selected_covers):
        for id_index, target_id in enumerate(ids):
            if cover_mask & (1 << id_index):
                assignment[target_id] = source_index
    for target_id in ids:
        assignment.setdefault(target_id, None)

    # This is the critical integrity invariant. Never write a partial plan.
    for destination, target_ids in archive_targets:
        coverage = [0] * source_count
        dummy_count = 0
        for target_id in target_ids:
            source_index = assignment[target_id]
            if source_index is None:
                dummy_count += 1
            else:
                coverage[source_index] += 1
        if coverage != [1] * source_count or dummy_count != len(target_ids) - source_count:
            raise MappingError(
                f"Internal mapping validation failed for {destination.name}; patch was not written."
            )

    return {
        "assignment": assignment,
        "unique_archive_sets": len(archive_sets),
        "unique_target_count": len(ids),
        "dummy_target_count": sum(source_index is None for source_index in assignment.values()),
        "solver_states": state_count,
    }


def collect_source_entries_and_body_types(sdk, scene):
    manager = sdk.Global_TocManager
    unit_id = int(sdk.UnitID)
    source_entries = []
    source_body_types = []
    ignored_dummy_ids = []
    HIDDEN_SOURCE_CACHE.clear()
    for source in active_sources(scene):
        # Source is intentionally resolved through the active patch first, so
        # a source Unit edited by the user is copied byte-for-byte.
        # Source Units were explicitly added from the active patch. Do not use
        # SearchAll here: HD2SDK would load whichever archive contains an ID.
        entry = manager.GetEntry(int(source.entry_id), unit_id, SearchAll=False, IgnorePatch=False)
        if entry is None:
            raise MappingError(f"Could not find source Unit {source.entry_id}")
        if is_hidden_dummy_unit(entry):
            ignored_dummy_ids.append(int(source.entry_id))
            continue
        source_entries.append(copy.deepcopy(entry))
        source_body_types.append(optional_entry_body_type(entry))
    return source_entries, source_body_types, ignored_dummy_ids


def collect_source_archive_entries(sdk, scene, details):
    """Read all source slots from the selected source archive(s), not from UI ticks."""
    manager = sdk.Global_TocManager
    unit_id = int(sdk.UnitID)
    source_entries = []
    source_keys = []
    seen_keys = {}
    for source_archive in scene.hd2_ms_source_archives:
        try:
            source_ids = get_destination_unit_ids(sdk, source_archive.archive_id)
        except Exception as error:
            raise MappingError(f"Could not read source archive {source_archive.name}: {error}") from error
        if not source_ids:
            raise MappingError(f"No Unit IDs found in source archive {source_archive.name}")
        slot_targets = archive_slot_targets(details, source_archive.archive_id, source_ids)
        for source_id, slot_key in sorted(slot_targets.items(), key=lambda item: item[1]):
            # Source archive denotes a clean game armor; do not accidentally
            # reuse an override from the active patch as its source data.
            entry = manager.GetEntry(source_id, unit_id, SearchAll=True, IgnorePatch=True)
            if entry is None:
                raise MappingError(f"Could not load source Unit {source_id} from {source_archive.name}")
            actual_body_type = optional_entry_body_type(entry)
            if (
                actual_body_type is not None
                and slot_key[0] != "Any"
                and actual_body_type != slot_key[0]
            ):
                raise MappingError(
                    f"Source Unit {source_id} BodyType is {actual_body_type}, but JSON expects "
                    f"{slot_key[0]}/{slot_key[1]}/{slot_key[2]}."
                )
            if slot_key in seen_keys:
                raise MappingError(
                    f"Source archives {seen_keys[slot_key]} and {source_archive.name} both provide "
                    f"{slot_key[0]}/{slot_key[1]}/{slot_key[2]}. Select one source archive."
                )
            seen_keys[slot_key] = source_archive.name
            source_entries.append(copy.deepcopy(entry))
            source_keys.append(slot_key)
    return source_entries, source_keys


def unit_rig_signature(entry):
    """References that must match before copying an entire skinned Unit blob."""
    data = bytes(entry.TocData)
    if len(data) < 40:
        raise MappingError(f"Unit {entry.FileID} has no readable rig header.")
    # Unit header: BonesRef at 8, CompositeRef at 16, StateMachineRef at 32.
    return (
        struct.unpack_from("<Q", data, 8)[0],
        struct.unpack_from("<Q", data, 16)[0],
        struct.unpack_from("<Q", data, 32)[0],
    )


def preserve_incompatible_rigs(sdk, plan, source_entries, preserve_incompatible=False):
    """Optionally preserve targets whose rig references differ from their source."""
    incompatible = []
    for target_id, action in list(plan["assignment"].items()):
        if action[0] == "preserve":
            continue
        target_entry = get_transient_unit_entry(target_id)
        source_entry = source_entries[action[1]]
        if unit_rig_signature(source_entry) != unit_rig_signature(target_entry):
            incompatible.append(target_id)
            if preserve_incompatible:
                plan["assignment"][target_id] = ("preserve", None)
    plan["override_target_ids"] = {
        target_id for target_id, action in plan["assignment"].items() if action[0] != "preserve"
    }
    plan["cross_body_target_count"] = sum(
        action[0] == "cross_body_source" for action in plan["assignment"].values()
    )
    plan["incompatible_rig_target_ids"] = incompatible
    return plan


def collect_target_body_types(sdk, target_ids):
    body_types = {}
    for target_id in target_ids:
        # Classify the original destination resource, never a prior swap in an
        # active patch. A BodyType is a property of the target slot.
        entry = get_transient_unit_entry(target_id)
        body_types[int(target_id)] = optional_entry_body_type(entry)
    return body_types


def solve_body_type_assignment(archive_targets, source_body_types, target_body_types):
    """Solve Slim/Stocky/Any independently, then combine their assignments."""
    source_indices_by_body = {}
    for source_index, body_type in enumerate(source_body_types):
        source_indices_by_body.setdefault(body_type, []).append(source_index)

    target_bodies = set(target_body_types.values())
    source_bodies = set(source_indices_by_body)
    missing_source_bodies = sorted(target_bodies - source_bodies)
    extra_source_bodies = sorted(source_bodies - target_bodies)
    if missing_source_bodies:
        raise MappingError(
            "Destination contains BodyType with no source Units: " + ", ".join(missing_source_bodies)
        )
    if extra_source_bodies:
        raise MappingError(
            "Source contains BodyType absent from destination: " + ", ".join(extra_source_bodies)
        )

    assignment = {}
    dummy_body_types = set()
    unique_target_count = 0
    dummy_target_count = 0
    unique_archive_sets = 0
    solver_states = 0

    for body_type in sorted(source_indices_by_body):
        source_indices = source_indices_by_body[body_type]
        body_archive_targets = []
        for destination, target_ids in archive_targets:
            body_targets = tuple(target_id for target_id in target_ids if target_body_types[target_id] == body_type)
            if not body_targets:
                raise MappingError(f"{destination.name} has no {body_type} target Units.")
            body_archive_targets.append((destination, body_targets))

        body_plan = solve_global_assignment(body_archive_targets, len(source_indices))
        unique_target_count += body_plan["unique_target_count"]
        dummy_target_count += body_plan["dummy_target_count"]
        unique_archive_sets += body_plan["unique_archive_sets"]
        solver_states += body_plan["solver_states"]
        for target_id, local_source_index in body_plan["assignment"].items():
            if local_source_index is None:
                assignment[target_id] = ("dummy", body_type)
                dummy_body_types.add(body_type)
            else:
                assignment[target_id] = ("source", source_indices[local_source_index])

    if len(assignment) != len(target_body_types):
        raise MappingError("BodyType mapping did not assign every destination Unit.")
    return {
        "assignment": assignment,
        "source_body_types": source_indices_by_body,
        "dummy_body_types": dummy_body_types,
        "unique_archive_sets": unique_archive_sets,
        "unique_target_count": unique_target_count,
        "dummy_target_count": dummy_target_count,
        "solver_states": solver_states,
    }


def find_external_uses(sdk, target_ids, selected_archive_ids):
    """Return archive packages outside the selection that contain patched IDs."""
    target_ids = set(target_ids)
    selected_archive_ids = {str(archive_id) for archive_id in selected_archive_ids}
    unit_id = int(sdk.UnitID)
    affected = []
    for archive in sdk.Global_TocManager.SearchArchives:
        archive_id = str(archive.Name)
        if archive_id in selected_archive_ids:
            continue
        hits = target_ids.intersection(archive.TocEntries.get(unit_id, []))
        if hits:
            try:
                friendly_name = sdk.GetArchiveNameFromID(archive_id) or archive_id
            except Exception:
                friendly_name = archive_id
            affected.append((friendly_name, archive_id, len(hits)))
    return sorted(affected, key=lambda item: (-item[2], item[0].lower()))


def make_dummy_unit_entry(source_entry, blender_options):
    """Build an invisible, valid Unit: one fully populated vertex per mesh and no indices."""
    if getattr(source_entry.LoadedData, "CompositeRef", 0):
        raise MappingError("The selected dummy template uses CompositeRef and cannot be safely reserialized.")
    dummy = copy.deepcopy(source_entry)
    for raw_mesh in dummy.LoadedData.RawMeshes:
        raw_mesh.VertexPositions = [[0.0, 0.0, 0.0]]
        raw_mesh.VertexNormals = [[0.0, 0.0, 1.0]]
        raw_mesh.VertexTangents = [[1.0, 0.0, 0.0]]
        raw_mesh.VertexBiTangents = [[0.0, 1.0, 0.0]]
        raw_mesh.VertexColors = [[0.0, 0.0, 0.0, 0.0]]
        raw_mesh.VertexUVs = [[[0.0, 0.0]] for _ in raw_mesh.VertexUVs]
        if raw_mesh.VertexBoneIndices or raw_mesh.VertexWeights:
            component_count = max(1, len(raw_mesh.VertexBoneIndices))
            raw_mesh.VertexBoneIndices = [[[0, 0, 0, 0]] for _ in range(component_count)]
            raw_mesh.VertexWeights = [[1.0, 0.0, 0.0, 0.0]]
        else:
            raw_mesh.VertexBoneIndices = []
            raw_mesh.VertexWeights = []
        raw_mesh.Indices = []
        for material in raw_mesh.Materials:
            material.StartIndex = 0
            material.NumIndices = 0

    # AutoLods would copy LOD0 over the intentionally empty LOD meshes.
    dummy_options = dict(blender_options)
    dummy_options["AutoLods"] = False
    dummy.Save(BlenderOpts=dummy_options)
    # Re-open the serialized result. This verifies the actual bytes, not only
    # the in-memory mesh lists used to construct it.
    dummy.Load(True, False)
    if not dummy.GpuData:
        raise MappingError("Invisible dummy Unit has no GPU payload.")
    for mesh_index, raw_mesh in enumerate(dummy.LoadedData.RawMeshes):
        if len(raw_mesh.VertexPositions) != 1 or raw_mesh.Indices:
            raise MappingError(f"Invisible dummy validation failed for mesh {mesh_index}.")
        if any(material.NumIndices != 0 for material in raw_mesh.Materials):
            raise MappingError(f"Invisible dummy still has indices in mesh {mesh_index}.")
    return dummy


def build_invisible_dummy_template(source_entries, scene):
    """Create one reusable hidden Unit payload from a selected source Unit."""
    settings = getattr(scene, "Hd2ToolPanelSettings", None)
    blender_options = settings.get_settings_dict() if settings is not None else {}
    for source_entry in source_entries:
        template = copy.deepcopy(source_entry)
        if not template.IsLoaded:
            template.Load(True, False)
        if getattr(template.LoadedData, "CompositeRef", 0):
            continue
        return make_dummy_unit_entry(template, blender_options)
    raise MappingError(
        "Could not build an invisible fallback Unit: every selected source uses CompositeRef."
    )


def validate_patch_offsets(patch):
    """Validate every final payload range before touching the user's files."""
    toc_size = len(patch.TocFile.Data)
    gpu_size = len(patch.GpuFile.Data)
    stream_size = len(patch.StreamFile.Data)
    for entries in patch.TocDict.values():
        for entry in entries.values():
            if entry.TocDataOffset + len(entry.TocData) > toc_size:
                raise MappingError(f"TOC payload for Unit {entry.FileID} is out of bounds.")
            if entry.GpuResourceOffset + len(entry.GpuData) > gpu_size:
                raise MappingError(f"GPU payload for Unit {entry.FileID} is out of bounds.")
            if entry.StreamOffset + len(entry.StreamData) > stream_size:
                raise MappingError(f"Stream payload for Unit {entry.FileID} is out of bounds.")
            if entry.GpuResourceOffset % 64 != 0 and entry.GpuData:
                raise MappingError(f"GPU payload for Unit {entry.FileID} is not 64-byte aligned.")
            if entry.StreamOffset % 64 != 0 and entry.StreamData:
                raise MappingError(f"Stream payload for Unit {entry.FileID} is not 64-byte aligned.")


def atomic_write(path, data):
    temporary_path = path + ".hd2ms.tmp"
    try:
        with open(temporary_path, "w+b") as file:
            file.write(data)
        os.replace(temporary_path, path)
    except Exception:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)
        raise


def write_deduplicated_patch(patch, sdk):
    """Write content-addressed payloads once, with every alias sharing offsets."""
    patch.TocFile = sdk.MemoryStream(IOMode="write")
    patch.GpuFile = sdk.MemoryStream(IOMode="write")
    patch.StreamFile = sdk.MemoryStream(IOMode="write")
    patch.Serialize(SerializeData=False)

    canonical_entries = {}
    unique_payloads = 0
    for entries in patch.TocDict.values():
        for entry in entries.values():
            digest, payload = payload_digest(entry)
            bucket = canonical_entries.setdefault(digest, [])
            canonical = next(
                (candidate for candidate, candidate_payload in bucket if candidate_payload == payload),
                None,
            )
            if canonical is None:
                entry.SerializeData(patch.TocFile, patch.GpuFile, patch.StreamFile)
                bucket.append((entry, payload))
                unique_payloads += 1
            else:
                entry.TocDataOffset = canonical.TocDataOffset
                entry.GpuResourceOffset = canonical.GpuResourceOffset
                entry.StreamOffset = canonical.StreamOffset

    # StreamToc.Serialize writes the TOC records once before and once after its
    # payloads. Re-write them here after our shared offsets have been assigned.
    toc_entry_start = 72 + len(patch.TocTypes) * 32
    patch.TocFile.seek(toc_entry_start)
    index = 1
    for toc_type in patch.TocTypes:
        for entry in patch.TocDict[toc_type.TypeID].values():
            entry.Serialize(patch.TocFile, index)
            index += 1

    num_entries = sum(len(entries) for entries in patch.TocDict.values())
    minimum_toc_size = 256 * num_entries
    if len(patch.TocFile.Data) < minimum_toc_size:
        patch.TocFile.Data.extend(bytearray(minimum_toc_size - len(patch.TocFile.Data)))
    validate_patch_offsets(patch)
    atomic_write(patch.Path, bytes(patch.TocFile.Data))
    atomic_write(patch.Path + ".gpu_resources", bytes(patch.GpuFile.Data))
    atomic_write(patch.Path + ".stream", bytes(patch.StreamFile.Data))
    return unique_payloads


def ensure_active_patch(sdk):
    manager = sdk.Global_TocManager
    if manager.ActivePatch is not None:
        return manager.ActivePatch
    base_archive_path = os.path.join(sdk.Global_gamepath, sdk.BaseArchiveHexID)
    base_archive = manager.LoadArchive(base_archive_path, SetActive=True)
    manager.SetActive(base_archive)
    manager.CreatePatchFromActive("Armor Multi Swap")
    return manager.ActivePatch


def managed_patch_properties(scene):
    if scene.hd2_ms_mode == "HELMET":
        return "hd2_ms_helmet_generated_patch_path", "hd2_ms_helmet_generated_ids"
    return "hd2_ms_generated_patch_path", "hd2_ms_generated_ids"


def remove_previous_managed_entries(patch, scene, unit_id):
    """Replace the prior run from this Blender scene without clearing user entries."""
    path_prop, ids_prop = managed_patch_properties(scene)
    if getattr(scene, path_prop) != patch.Path:
        return
    for value in getattr(scene, ids_prop).split(","):
        if value.isdigit():
            patch.RemoveEntry(int(value), unit_id, ReloadUI=False)


def remember_managed_entries(scene, patch, target_ids):
    path_prop, ids_prop = managed_patch_properties(scene)
    setattr(scene, path_prop, patch.Path)
    setattr(scene, ids_prop, ",".join(str(target_id) for target_id in sorted(target_ids)))


class HD2MS_SourceItem(PropertyGroup):
    entry_id: StringProperty(name="Entry ID")
    type_id: StringProperty(name="Type ID")
    label: StringProperty(name="Armor")


class HD2MS_ArchiveItem(PropertyGroup):
    archive_id: StringProperty(name="Archive ID")
    name: StringProperty(name="Archive")


class HD2MS_UL_Sources(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=item.label, icon='MESH_DATA')
        remove = row.operator("hd2_multi_swap.remove_source", text="", icon='X')
        remove.index = index


class HD2MS_UL_Destinations(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=item.name, icon='FILE_FOLDER')
        remove = row.operator("hd2_multi_swap.remove_destination", text="", icon='X')
        remove.index = index

    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        search = context.scene.hd2_ms_destination_filter.strip().lower()
        if not search:
            return [], []
        flags = [
            self.bitflag_filter_item if search in f"{item.name} {item.archive_id}".lower() else 0
            for item in items
        ]
        return flags, []


class HD2MS_UL_SourceArchives(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=item.name, icon='FILE_FOLDER')
        remove = row.operator("hd2_multi_swap.remove_source_archive", text="", icon='X')
        remove.index = index


class HD2MS_OT_AddUnitsForSwap(Operator):
    bl_idname = "hd2_multi_swap.add_units_for_swap"
    bl_label = "Add Unit(s) for ID Swap"
    bl_description = "Add the selected HD2SDK Unit entries as source armor Units"

    entry_ids: StringProperty(options={'HIDDEN'})

    def execute(self, context):
        sdk = get_sdk()
        if sdk is None:
            self.report({'ERROR'}, "HD2SDK is not enabled or could not be imported")
            return {'CANCELLED'}
        try:
            entry_ids = [int(entry_id) for entry_id in self.entry_ids.split(",") if entry_id]
        except ValueError:
            self.report({'ERROR'}, "The selected Unit ID is invalid")
            return {'CANCELLED'}
        added = add_source_units(sdk, context.scene, entry_ids)
        if added == 0:
            self.report({'WARNING'}, "The selected Unit entries are already in the source list")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Added {added} source Unit{'s' if added != 1 else ''}")
        return {'FINISHED'}


class HD2MS_OT_CaptureSelectedUnits(Operator):
    bl_idname = "hd2_multi_swap.capture_selected_units"
    bl_label = "Add Unit Entries Already in Patch"
    bl_description = "Add all Unit entries marked as already included in HD2SDK's active patch"

    def execute(self, context):
        sdk = get_sdk()
        if sdk is None:
            self.report({'ERROR'}, "HD2SDK is not enabled or could not be imported")
            return {'CANCELLED'}
        unit_id = int(sdk.UnitID)
        ui_list = getattr(context.scene, f"list_{unit_id}", [])
        manager = sdk.Global_TocManager
        entry_ids = []
        for item in ui_list:
            entry = manager.GetEntry(int(item.item_name), unit_id, SearchAll=True, IgnorePatch=False)
            if entry is not None and manager.IsInPatch(entry):
                entry_ids.append(int(item.item_name))
        added = add_source_units(sdk, context.scene, entry_ids)
        if added == 0:
            self.report({'WARNING'}, "No new Unit entries already in the active patch were found")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Added {added} source Unit{'s' if added != 1 else ''} already in patch")
        return {'FINISHED'}


class HD2MS_OT_AddDestinationArchive(Operator):
    bl_idname = "hd2_multi_swap.add_destination_archive"
    bl_label = "Add Destination Archive"
    bl_description = "Add this archive to the destination list without closing the archive browser"

    archive_id: StringProperty(options={'HIDDEN'})
    archive_name: StringProperty(options={'HIDDEN'})

    def execute(self, context):
        try:
            details, _ = load_armor_list(active_dataset_mode(context.scene))
            selected = details.get(str(self.archive_id).lower(), {})
            family_name = str(selected.get("name") or self.archive_name)
            family_archives = [
                (archive_id, str(data.get("name") or archive_id))
                for archive_id, data in details.items()
                if str(data.get("name") or "").casefold() == family_name.casefold()
            ]
        except MappingError:
            family_name = self.archive_name
            family_archives = []

        # A friendly armor name can represent Slim/Stocky variants stored in
        # different package IDs. Selecting it must cover the complete family.
        if not family_archives:
            family_archives = [(str(self.archive_id).lower(), self.archive_name)]
        if is_unknown_helmet(context.scene, family_name):
            self.report({'INFO'}, "Unknown Helmet entries are excluded from Helmet mode")
            return {'CANCELLED'}

        added = 0
        for archive_id, archive_name in family_archives:
            if contains_destination(active_destinations(context.scene), archive_id):
                continue
            item = active_destinations(context.scene).add()
            item.archive_id = archive_id
            item.name = archive_name
            added += 1
        if not added:
            self.report({'INFO'}, f"All {family_name} archive variants are already in the destination list")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Added {added} archive variant(s) for {family_name}")
        return {'FINISHED'}


class HD2MS_OT_AddDestinationArmorClass(Operator):
    bl_idname = "hd2_multi_swap.add_destination_armor_class"
    bl_label = "Add Destination Armor Class"
    bl_description = "Add every armor archive in this class to Destination archives"

    armor_class: StringProperty(options={'HIDDEN'})

    def execute(self, context):
        try:
            _, categories = load_armor_list(active_dataset_mode(context.scene))
            archives = categories[self.armor_class]
        except (KeyError, MappingError) as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}

        added = 0
        for archive_id, archive_name in archives:
            if is_unknown_helmet(context.scene, archive_name):
                continue
            if contains_destination(active_destinations(context.scene), archive_id):
                continue
            item = active_destinations(context.scene).add()
            item.archive_id = archive_id
            item.name = archive_name
            added += 1
        self.report({'INFO'}, f"Added {added} {self.armor_class} destination archive(s)")
        return {'FINISHED'}


class HD2MS_OT_AddSourceArchive(Operator):
    bl_idname = "hd2_multi_swap.add_source_archive"
    bl_label = "Add Source Archive"
    bl_description = "Use this armor archive as the automatic source-slot set"

    archive_id: StringProperty(options={'HIDDEN'})
    archive_name: StringProperty(options={'HIDDEN'})

    def execute(self, context):
        if contains_destination(context.scene.hd2_ms_source_archives, self.archive_id):
            self.report({'INFO'}, "Archive is already in the source list")
            return {'CANCELLED'}
        item = context.scene.hd2_ms_source_archives.add()
        item.archive_id = self.archive_id
        item.name = self.archive_name
        self.report({'INFO'}, f"Added source archive: {self.archive_name}")
        return {'FINISHED'}


class HD2MS_OT_BrowseArchives(Operator):
    bl_idname = "hd2_multi_swap.browse_archives"
    bl_label = "Search Found Archives"
    bl_description = "Search HD2SDK's archive hash list and add one or more destination archives"

    search_query: StringProperty(
        name="Search",
        default="",
        options={'TEXTEDIT_UPDATE'},
    )
    source_mode: BoolProperty(options={'HIDDEN'}, default=False)

    def invoke(self, context, event):
        self.search_query = ""
        return context.window_manager.invoke_popup(self, width=640)

    def execute(self, context):
        return {'FINISHED'}

    def draw(self, context):
        layout = self.layout
        sdk = get_sdk()
        if sdk is None:
            layout.label(text="HD2SDK was not detected.", icon='ERROR')
            return

        layout.prop(self, "search_query", icon='VIEWZOOM')
        query = self.search_query.strip().lower()
        if not query:
            layout.label(text="Type an archive name or ID to search.", icon='INFO')
            return

        matches = []
        for archive_id, archive_name in sdk.Global_ArchiveHashes:
            archive_id = str(archive_id)
            archive_name = str(archive_name) if archive_name else archive_id
            if query in archive_name.lower() or query in archive_id.lower():
                matches.append((archive_name, archive_id))
        matches.sort(key=lambda archive: archive[0].lower())

        if not matches:
            layout.label(text="No archive found.", icon='INFO')
            return

        if len(matches) > 100:
            layout.label(text=f"Showing first 100 of {len(matches)} matches; refine the search.", icon='INFO')
        for archive_name, archive_id in matches[:100]:
            row = layout.row(align=True)
            row.label(text=archive_name, icon='FILE_FOLDER')
            operator_id = "hd2_multi_swap.add_source_archive" if self.source_mode else "hd2_multi_swap.add_destination_archive"
            add = row.operator(operator_id, text="Add", icon='ADD')
            add.archive_id = archive_id
            add.archive_name = archive_name


def collect_archive_targets(sdk, scene):
    archive_targets = []
    for destination in active_destinations(scene):
        try:
            target_ids = get_destination_unit_ids(sdk, destination.archive_id)
        except Exception as error:
            raise MappingError(f"Could not read destination archive {destination.name}: {error}") from error
        if not target_ids:
            raise MappingError(f"No Unit IDs found in destination archive {destination.name}")
        archive_targets.append((destination, tuple(dict.fromkeys(int(target_id) for target_id in target_ids))))
    return archive_targets


def analyze_mapping(sdk, scene):
    if not active_sources(scene):
        raise MappingError("Add at least one source Unit from HD2SDK first")
    if not active_destinations(scene):
        raise MappingError("Add at least one destination archive first")
    clear_transient_archives()
    try:
        details, _ = load_armor_list(active_dataset_mode(scene))
        archive_targets = collect_archive_targets(sdk, scene)
        source_entries, source_body_types, ignored_dummy_ids = collect_source_entries_and_body_types(sdk, scene)
        if not source_entries:
            raise MappingError(
                "Every selected source Unit is an invisible dummy. Add at least one source Unit with real geometry."
            )
        source_keys = source_slot_keys(details, source_entries, source_body_types)
        destination_slot_targets = {
            str(destination.archive_id).lower(): archive_slot_targets(details, destination.archive_id, target_ids)
            for destination, target_ids in archive_targets
        }
        plan = solve_slot_assignment(
            archive_targets,
            source_keys,
            destination_slot_targets,
            # When one body type is absent from the source, reuse the matching
            # slot/layer from the other body type before using spare/dummy data.
            allow_cross_body_fallback=True,
        )
        plan["ignored_dummy_source_ids"] = ignored_dummy_ids
        external_uses = find_external_uses(
            sdk,
            plan["override_target_ids"],
            [destination.archive_id for destination, _ in archive_targets],
        )
        return archive_targets, plan, external_uses, source_entries
    finally:
        clear_transient_archives()


def format_analysis(plan, source_count, archive_count, external_uses):
    slot_count = len(set(plan["source_slot_keys"]))
    skipped = plan["skipped_source_keys"]
    skipped_summary = ""
    if skipped:
        sample = ", ".join("/".join(key) for key in skipped[:3])
        extra = "" if len(skipped) <= 3 else f" +{len(skipped) - 3}"
        skipped_summary = f" Skipped {len(skipped)} source slot(s) absent from destinations ({sample}{extra})."
    cross_body_summary = ""
    if plan["cross_body_target_count"]:
        cross_body_summary = f" {plan['cross_body_target_count']} target ID(s) use cross-body source fallback."
    spare_summary = ""
    if plan.get("spare_source_target_key_count"):
        spare_summary = (
            f" {plan['spare_source_target_key_count']} missing slot(s) use otherwise-unused source Units."
        )
    dummy_summary = ""
    if plan.get("dummy_target_count"):
        dummy_summary = f" {plan['dummy_target_count']} target ID(s) use the hidden dummy fallback."
    ignored_source_summary = ""
    if plan.get("ignored_dummy_source_ids"):
        ignored_source_summary = (
            f" Ignored {len(plan['ignored_dummy_source_ids'])} pre-hidden source Unit(s)."
        )
    rig_summary = ""
    if plan.get("incompatible_rig_target_ids"):
        rig_summary = f" {len(plan['incompatible_rig_target_ids'])} target ID(s) have differing rig refs."
    override_count = len(plan["override_target_ids"])
    return (
        f"PASS — {source_count} source payloads in {slot_count} semantic slot(s) cover "
        f"{archive_count} destination archive(s); "
        f"{override_count} override ID(s), {plan['target_count'] - override_count} preserved target ID(s), "
        f"{len(external_uses)} external archive package(s) share patched IDs."
        f"{cross_body_summary}{spare_summary}{dummy_summary}{rig_summary}{skipped_summary}{ignored_source_summary}"
    )


class HD2MS_OT_AnalyzeIdSwapMapping(Operator):
    bl_idname = "hd2_multi_swap.analyze_id_swap_mapping"
    bl_label = "Analyze Global Mapping"
    bl_description = "Verify JSON slot mapping before any patch data is written"

    def execute(self, context):
        sdk = get_sdk()
        if sdk is None:
            self.report({'ERROR'}, "HD2SDK is not enabled or could not be imported")
            return {'CANCELLED'}
        try:
            archive_targets, plan, external_uses, _ = analyze_mapping(sdk, context.scene)
        except MappingError as error:
            context.scene.hd2_ms_analysis = f"BLOCKED — {error}"
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}

        summary = format_analysis(plan, len(active_sources(context.scene)), len(archive_targets), external_uses)
        context.scene.hd2_ms_analysis = summary
        if external_uses:
            sample = ", ".join(name for name, _, _ in external_uses[:3])
            self.report({'WARNING'}, f"{summary} Shared examples: {sample}")
        else:
            self.report({'INFO'}, summary)
        return {'FINISHED'}


class HD2MS_OT_GenerateIdSwapPatch(Operator):
    bl_idname = "hd2_multi_swap.generate_id_swap_patch"
    bl_label = "Generate Deduplicated ID-Swap Patch"
    bl_description = "Replace matching BodyType/slot/layer targets and hide unmatched slots"

    def execute(self, context):
        sdk = get_sdk()
        scene = context.scene
        if sdk is None:
            self.report({'ERROR'}, "HD2SDK is not enabled or could not be imported")
            return {'CANCELLED'}

        try:
            archive_targets, plan, external_uses, source_entries = analyze_mapping(sdk, scene)
        except MappingError as error:
            scene.hd2_ms_analysis = f"BLOCKED — {error}"
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}

        unit_id = int(sdk.UnitID)
        try:
            patch = ensure_active_patch(sdk)
            remove_previous_managed_entries(patch, scene, unit_id)
            dummy_template = None
            if any(action[0] == "dummy" for action in plan["assignment"].values()):
                dummy_template = build_invisible_dummy_template(source_entries, scene)

            for target_id, action in plan["assignment"].items():
                action_type, value = action
                if action_type == "preserve":
                    continue
                replacement = (
                    copy.deepcopy(dummy_template)
                    if action_type == "dummy"
                    else copy.deepcopy(source_entries[value])
                )
                replacement.FileID = int(target_id)
                replacement.TypeID = unit_id
                patch.AddEntry(replacement, override=True, ReloadUI=False)

            unique_payloads = write_deduplicated_patch(patch, sdk)
            remember_managed_entries(scene, patch, plan["override_target_ids"])
            sdk.LoadEntryLists()
        except (MappingError, OSError, RuntimeError, ValueError) as error:
            self.report({'ERROR'}, f"Patch was not written: {error}")
            return {'CANCELLED'}

        summary = format_analysis(plan, len(source_entries), len(archive_targets), external_uses)
        scene.hd2_ms_analysis = summary
        self.report(
            {'INFO'},
            f"Wrote {len(plan['override_target_ids'])} Unit overrides with {unique_payloads} stored payloads."
        )
        return {'FINISHED'}


class HD2MS_OT_RemoveSource(Operator):
    bl_idname = "hd2_multi_swap.remove_source"
    bl_label = "Remove Source"

    index: IntProperty(options={'HIDDEN'})

    def execute(self, context):
        sources = active_sources(context.scene)
        if 0 <= self.index < len(sources):
            sources.remove(self.index)
            setattr(context.scene, active_source_index_property(context.scene), max(0, self.index - 1))
        return {'FINISHED'}


class HD2MS_OT_RemoveSourceArchive(Operator):
    bl_idname = "hd2_multi_swap.remove_source_archive"
    bl_label = "Remove Source Archive"

    index: IntProperty(options={'HIDDEN'})

    def execute(self, context):
        source_archives = context.scene.hd2_ms_source_archives
        if 0 <= self.index < len(source_archives):
            source_archives.remove(self.index)
            context.scene.hd2_ms_source_archive_index = max(0, self.index - 1)
        return {'FINISHED'}


class HD2MS_OT_RemoveDestination(Operator):
    bl_idname = "hd2_multi_swap.remove_destination"
    bl_label = "Remove Destination"

    index: IntProperty(options={'HIDDEN'})

    def execute(self, context):
        destinations = active_destinations(context.scene)
        if 0 <= self.index < len(destinations):
            destinations.remove(self.index)
            setattr(context.scene, active_destination_index_property(context.scene), max(0, self.index - 1))
        return {'FINISHED'}


class HD2MS_OT_ClearSources(Operator):
    bl_idname = "hd2_multi_swap.clear_sources"
    bl_label = "Clear Sources"

    def execute(self, context):
        active_sources(context.scene).clear()
        setattr(context.scene, active_source_index_property(context.scene), 0)
        return {'FINISHED'}


class HD2MS_OT_ClearSourceArchives(Operator):
    bl_idname = "hd2_multi_swap.clear_source_archives"
    bl_label = "Clear Source Archives"

    def execute(self, context):
        context.scene.hd2_ms_source_archives.clear()
        context.scene.hd2_ms_source_archive_index = 0
        return {'FINISHED'}


class HD2MS_OT_ClearDestinations(Operator):
    bl_idname = "hd2_multi_swap.clear_destinations"
    bl_label = "Clear Destination Archives"

    def execute(self, context):
        active_destinations(context.scene).clear()
        setattr(context.scene, active_destination_index_property(context.scene), 0)
        return {'FINISHED'}


class HD2MS_OT_OpenSupportLink(Operator):
    bl_idname = "hd2_multi_swap.open_support_link"
    bl_label = "Open Support Link"
    bl_description = "Open the creator's support page in your web browser"

    url: StringProperty(options={'HIDDEN'})

    def execute(self, context):
        bpy.ops.wm.url_open(url=self.url)
        return {'FINISHED'}


def draw_sdk_unit_context_menu(menu, context):
    """Append ID-swap actions to HD2SDK's right-click menu for Unit list items."""
    sdk = get_sdk()
    button_operator = getattr(context, "button_operator", None)
    # HD2SDK itself identifies this context target by its generated operator
    # class name; ``bl_idname`` is not consistently exposed here by Blender.
    if sdk is None or type(button_operator).__name__ != "HELLDIVER2_OT_archive_entry":
        return

    list_id = getattr(button_operator, "list_id", "")
    list_index = getattr(button_operator, "list_index", -1)
    ui_list = getattr(context.scene, list_id, None)
    if ui_list is None or not (0 <= list_index < len(ui_list)):
        return
    clicked_item = ui_list[list_index]
    if int(clicked_item.item_type) != int(sdk.UnitID):
        return

    selected_items = [item for item in ui_list if item.item_selected and int(item.item_type) == int(sdk.UnitID)]
    if not selected_items:
        selected_items = [clicked_item]
    entry_ids = ",".join(item.item_name for item in selected_items)
    text = "Add Unit for ID Swap" if len(selected_items) == 1 else f"Add {len(selected_items)} Units for ID Swap"

    menu.layout.separator()
    operator = menu.layout.operator("hd2_multi_swap.add_units_for_swap", text=text, icon='ADD')
    operator.entry_ids = entry_ids


class HD2MS_PT_MainPanel(Panel):
    bl_label = "HD2_Mass_ID_Swap"
    bl_idname = "HD2MS_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ID_Swap'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        support_box = layout.box()
        support_box.label(text="Created by Uskummel", icon='USER')
        support_box.label(text="If this saved your time:", icon='FUND')
        support_row = support_box.row(align=True)
        paypal = support_row.operator(
            "hd2_multi_swap.open_support_link",
            text="Buy me a coffee (PayPal)",
            icon_value=support_icon_value("paypal"),
        )
        paypal.url = "http://paypal.me/uskummel"
        kofi = support_row.operator(
            "hd2_multi_swap.open_support_link",
            text="Buy me a coffee (Ko-fi)",
            icon_value=support_icon_value("kofi"),
        )
        kofi.url = "https://ko-fi.com/uskummel"

        sdk = get_sdk()
        if sdk is None:
            layout.label(text="HD2SDK was not detected.", icon='ERROR')
            layout.label(text="Enable HD2SDK Community Edition, then reload this addon.")
            return

        mode_row = layout.row(align=True)
        mode_row.prop(scene, "hd2_ms_mode", expand=True)
        source_prop = "hd2_ms_helmet_sources" if scene.hd2_ms_mode == "HELMET" else "hd2_ms_sources"
        source_index_prop = active_source_index_property(scene)
        destination_prop = "hd2_ms_helmet_destinations" if scene.hd2_ms_mode == "HELMET" else "hd2_ms_destinations"
        destination_index_prop = active_destination_index_property(scene)
        mode_label = "Helmet" if scene.hd2_ms_mode == "HELMET" else "Armor"

        source_box = layout.box()
        source_box.label(text=f"1. Source {mode_label} Units", icon='MESH_DATA')
        source_box.operator("hd2_multi_swap.capture_selected_units", icon='ADD')
        source_box.template_list(
            "HD2MS_UL_Sources", "", scene, source_prop, scene,
            source_index_prop, rows=4,
        )
        source_box.operator("hd2_multi_swap.clear_sources", icon='TRASH', text="Clear source list")

        destination_box = layout.box()
        row = destination_box.row(align=True)
        row.label(text=f"2. Destination {mode_label} archives", icon='FILE_FOLDER')
        row.operator("hd2_multi_swap.browse_archives", text="", icon='ADD')
        class_row = destination_box.row(align=True)
        for armor_class, label in (("light", "Light"), ("medium", "Medium"), ("heavy", "Heavy")):
            add_class = class_row.operator(
                "hd2_multi_swap.add_destination_armor_class",
                text=label,
                icon='ADD',
            )
            add_class.armor_class = armor_class
        destination_box.prop(scene, "hd2_ms_destination_filter", text="", icon='VIEWZOOM')
        destination_box.template_list(
            "HD2MS_UL_Destinations", "", scene, destination_prop, scene,
            destination_index_prop, rows=6,
        )
        destination_box.operator("hd2_multi_swap.clear_destinations", icon='TRASH')

        if scene.hd2_ms_analysis:
            analysis_box = layout.box()
            for line in scene.hd2_ms_analysis.split("; "):
                analysis_box.label(text=line, icon='INFO')

        write_box = layout.box()
        write_box.label(text="3. Write patch", icon='FILE_TICK')
        generate_row = write_box.row()
        generate_row.enabled = bool(active_sources(scene) and active_destinations(scene))
        generate_row.operator(
            "hd2_multi_swap.generate_id_swap_patch",
            text="Generate & Write ID-Swap Patch",
            icon='FILE_TICK',
        )
        layout.label(text=f"Connected to {sdk.__name__}", icon='CHECKMARK')

CLASSES = (
    HD2MS_SourceItem,
    HD2MS_ArchiveItem,
    HD2MS_UL_Sources,
    HD2MS_UL_Destinations,
    HD2MS_UL_SourceArchives,
    HD2MS_OT_AddUnitsForSwap,
    HD2MS_OT_CaptureSelectedUnits,
    HD2MS_OT_AddDestinationArchive,
    HD2MS_OT_AddDestinationArmorClass,
    HD2MS_OT_AddSourceArchive,
    HD2MS_OT_BrowseArchives,
    HD2MS_OT_AnalyzeIdSwapMapping,
    HD2MS_OT_GenerateIdSwapPatch,
    HD2MS_OT_RemoveSource,
    HD2MS_OT_RemoveSourceArchive,
    HD2MS_OT_RemoveDestination,
    HD2MS_OT_ClearSources,
    HD2MS_OT_ClearSourceArchives,
    HD2MS_OT_ClearDestinations,
    HD2MS_OT_OpenSupportLink,
    HD2MS_PT_MainPanel,
)


def register():
    global SUPPORT_ICONS
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    SUPPORT_ICONS = bpy.utils.previews.new()
    icon_folder = os.path.join(bpy.app.tempdir, "hd2_armor_multi_swap_icons")
    os.makedirs(icon_folder, exist_ok=True)
    for icon_name in ("paypal", "kofi"):
        icon_path = os.path.join(icon_folder, f"{icon_name}.png")
        with open(icon_path, "wb") as icon_file:
            icon_file.write(base64.b64decode(EMBEDDED_SUPPORT_ICONS[icon_name]))
        SUPPORT_ICONS.load(icon_name, icon_path, 'IMAGE')
    bpy.types.Scene.hd2_ms_sources = CollectionProperty(type=HD2MS_SourceItem)
    bpy.types.Scene.hd2_ms_source_index = IntProperty(default=0)
    bpy.types.Scene.hd2_ms_helmet_sources = CollectionProperty(type=HD2MS_SourceItem)
    bpy.types.Scene.hd2_ms_helmet_source_index = IntProperty(default=0)
    bpy.types.Scene.hd2_ms_source_archives = CollectionProperty(type=HD2MS_ArchiveItem)
    bpy.types.Scene.hd2_ms_source_archive_index = IntProperty(default=0)
    bpy.types.Scene.hd2_ms_destinations = CollectionProperty(type=HD2MS_ArchiveItem)
    bpy.types.Scene.hd2_ms_destination_index = IntProperty(default=0)
    bpy.types.Scene.hd2_ms_helmet_destinations = CollectionProperty(type=HD2MS_ArchiveItem)
    bpy.types.Scene.hd2_ms_helmet_destination_index = IntProperty(default=0)
    bpy.types.Scene.hd2_ms_mode = EnumProperty(
        name="Mode",
        items=(("ARMOR", "Armor", "Swap armor body Units"), ("HELMET", "Helmet", "Swap helmet Units")),
        default="ARMOR",
    )
    bpy.types.Scene.hd2_ms_destination_filter = StringProperty(
        name="Search destination archives",
        description="Filter the destination list by friendly archive name or ID",
        default="",
    )
    bpy.types.Scene.hd2_ms_analysis = StringProperty(default="")
    bpy.types.Scene.hd2_ms_generated_ids = StringProperty(default="")
    bpy.types.Scene.hd2_ms_generated_patch_path = StringProperty(default="")
    bpy.types.Scene.hd2_ms_helmet_generated_ids = StringProperty(default="")
    bpy.types.Scene.hd2_ms_helmet_generated_patch_path = StringProperty(default="")
    context_menu = getattr(bpy.types, "WM_MT_button_context", None)
    if context_menu is not None:
        context_menu.append(draw_sdk_unit_context_menu)


def unregister():
    global SUPPORT_ICONS
    context_menu = getattr(bpy.types, "WM_MT_button_context", None)
    if context_menu is not None:
        try:
            context_menu.remove(draw_sdk_unit_context_menu)
        except ValueError:
            pass
    for prop in (
        "hd2_ms_destination_filter",
        "hd2_ms_mode",
        "hd2_ms_generated_patch_path",
        "hd2_ms_generated_ids",
        "hd2_ms_helmet_generated_patch_path",
        "hd2_ms_helmet_generated_ids",
        "hd2_ms_analysis",
        "hd2_ms_destination_index",
        "hd2_ms_destinations",
        "hd2_ms_helmet_destination_index",
        "hd2_ms_helmet_destinations",
        "hd2_ms_source_archive_index",
        "hd2_ms_source_archives",
        "hd2_ms_source_index",
        "hd2_ms_sources",
        "hd2_ms_helmet_source_index",
        "hd2_ms_helmet_sources",
    ):
        delattr(bpy.types.Scene, prop)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    if SUPPORT_ICONS is not None:
        bpy.utils.previews.remove(SUPPORT_ICONS)
        SUPPORT_ICONS = None


if __name__ == "__main__":
    register()
