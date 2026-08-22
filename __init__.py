if __package__:
    from .lfgg_nodes.dimensions_by_aspect_ratio import DimensionsByAspectRatio
    from .lfgg_nodes.image_dimensions import (
        ImageDimensionsByLongSide,
        ImageDimensionsByPixelBudget,
        ResizeImageByLongSide,
    )
    from .lfgg_nodes.load_and_crop_image import LoadAndCropImage
    from .lfgg_nodes.power_lora_loader_folder import PowerLoraLoaderFolder
    from .lfgg_nodes.prompt_composer import PromptComposer
    from .lfgg_nodes.routing_organizer import RoutingOrganizer
    from .lfgg_nodes.save_image_dynamic import SaveImageDynamic
    from .lfgg_nodes.string_join import StringJoin
    from .lfgg_nodes.string_replace import StringReplace, StringReplaceRegex
    from .lfgg_nodes.switches import BooleanSwitch, IndexSwitch
    from .lfgg_nodes.value_inspector import ValueInspector
    from .lfgg_nodes.video_cutter import VideoCutter
else:
    from lfgg_nodes.dimensions_by_aspect_ratio import DimensionsByAspectRatio
    from lfgg_nodes.image_dimensions import (
        ImageDimensionsByLongSide,
        ImageDimensionsByPixelBudget,
        ResizeImageByLongSide,
    )
    from lfgg_nodes.load_and_crop_image import LoadAndCropImage
    from lfgg_nodes.power_lora_loader_folder import PowerLoraLoaderFolder
    from lfgg_nodes.prompt_composer import PromptComposer
    from lfgg_nodes.routing_organizer import RoutingOrganizer
    from lfgg_nodes.save_image_dynamic import SaveImageDynamic
    from lfgg_nodes.string_join import StringJoin
    from lfgg_nodes.string_replace import StringReplace, StringReplaceRegex
    from lfgg_nodes.switches import BooleanSwitch, IndexSwitch
    from lfgg_nodes.value_inspector import ValueInspector
    from lfgg_nodes.video_cutter import VideoCutter


def _merge_class_mappings(*mappings):
    merged = {}
    for mapping in mappings:
        for node_id, node_class in mapping.items():
            if node_id in merged:
                raise RuntimeError(f"Duplicate node ID: {node_id}")
            merged[node_id] = node_class
    return merged


NODE_CLASS_MAPPINGS = _merge_class_mappings(
    {"LFGG_DimensionsByAspectRatio": DimensionsByAspectRatio},
    {"LFGG_ImageDimensionsByLongSide": ImageDimensionsByLongSide},
    {"LFGG_ImageDimensionsByPixelBudget": ImageDimensionsByPixelBudget},
    {"LFGG_ResizeImageByLongSide": ResizeImageByLongSide},
    {"LFGG_LoadAndCropImage": LoadAndCropImage},
    {"LFGG_PowerLoraLoaderFolder": PowerLoraLoaderFolder},
    {"LFGG_PromptComposer": PromptComposer},
    {"LFGG_RoutingOrganizer": RoutingOrganizer},
    {"LFGG_SaveImageDynamic": SaveImageDynamic},
    {"LFGG_StringJoin": StringJoin},
    {"LFGG_StringReplace": StringReplace},
    {"LFGG_StringReplaceRegex": StringReplaceRegex},
    {"LFGG_BooleanSwitch": BooleanSwitch},
    {"LFGG_IndexSwitch": IndexSwitch},
    {"LFGG_ValueInspector": ValueInspector},
    {"LFGG_VideoCutter": VideoCutter},
)
NODE_DISPLAY_NAME_MAPPINGS = {
    "LFGG_DimensionsByAspectRatio": "LFGG Dimensions by Aspect Ratio",
    "LFGG_ImageDimensionsByLongSide": "LFGG Image Dimensions by Long Side",
    "LFGG_ImageDimensionsByPixelBudget": "LFGG Image Dimensions by Pixel Budget",
    "LFGG_ResizeImageByLongSide": "LFGG Resize Image by Long Side",
    "LFGG_LoadAndCropImage": "LFGG Load and Crop Image",
    "LFGG_PowerLoraLoaderFolder": "LFGG Power LoRA Loader (Folder)",
    "LFGG_PromptComposer": "LFGG Prompt Composer",
    "LFGG_RoutingOrganizer": "LFGG Routing Organizer",
    "LFGG_SaveImageDynamic": "LFGG Save Image Dynamic",
    "LFGG_StringJoin": "LFGG String Join",
    "LFGG_StringReplace": "LFGG String Replace",
    "LFGG_StringReplaceRegex": "LFGG String Replace (Regex)",
    "LFGG_BooleanSwitch": "LFGG Boolean Switch",
    "LFGG_IndexSwitch": "LFGG Index Switch",
    "LFGG_ValueInspector": "LFGG Value Inspector",
    "LFGG_VideoCutter": "LFGG Video Cutter",
}
WEB_DIRECTORY = "./web"

__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "WEB_DIRECTORY",
]
