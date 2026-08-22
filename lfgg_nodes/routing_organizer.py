class RoutingOrganizer:
    CATEGORY = "LFGG/workflow"
    DESCRIPTION = (
        "Keeps labeled workflow connections aligned without changing their values."
    )
    FUNCTION = "route"
    RETURN_TYPES = ()

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}}

    def route(self):
        return ()
