from ..services import audience


class AudienceController:
    overview = staticmethod(audience.audience_overview)
    get = staticmethod(audience.get_version)
    create = staticmethod(audience.create_version)
