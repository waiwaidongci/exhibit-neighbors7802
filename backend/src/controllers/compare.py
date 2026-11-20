from ..services import compare


class CompareController:
    list = staticmethod(compare.list_comparisons)
    get = staticmethod(compare.get_comparison)
    create = staticmethod(compare.create_comparison)
