if __package__:
    from .lfgg_nodes.dimensions_by_aspect_ratio import DimensionsByAspectRatio
else:
    from lfgg_nodes.dimensions_by_aspect_ratio import DimensionsByAspectRatio


def _merge_class_mappings(*mappings):
    merged = {}
    for mapping in mappings:
        for node_id, node_class in mapping.items():
            if node_id in merged:
                raise RuntimeError(f"Duplicate node ID: {node_id}")
            merged[node_id] = node_class
    return merged


NODE_CLASS_MAPPINGS = _merge_class_mappings(
    {"LFGG_DimensionsByAspectRatio": DimensionsByAspectRatio}
)
NODE_DISPLAY_NAME_MAPPINGS = {
    "LFGG_DimensionsByAspectRatio": "LFGG Dimensions by Aspect Ratio"
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
