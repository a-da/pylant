import ciur
from ciur.shortcuts import pretty_parse_from_resources
import sys


def main_example():
    with ciur.open_file("example.org.ciur", __file__) as f:
        print(pretty_parse_from_resources(
                f,
                "http://example.org"
        ))


def patch():
    from pylant import PlantPatch
    from pathlib import Path
    plant = PlantPatch(Path(__file__).parent)

    main_import = __import__(__name__)

    modules = plant.locate_all_modules(
        main_import,
        ciur,
        ignore_modules=[]
    )
    plant.patch_modules(*modules)
    return plant


def patched_example():
    plant = patch()
    main_example()
    plant.save()


def exper():
    import ciur.rule

    class A(ciur.rule.Rule):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

        def __getattribute__(self, name: str):
            return object.__getattribute__(self, name)

    a = A(name='a', selector='xpath', type_list_=['+1'])
    A.from_list([])


if __name__ == '__main__':
    # exper()
    if sys.argv[1] == 'main-example':
        main_example()
    elif sys.argv[1] == 'patched-example':
        patched_example()
    else:
        raise NotImplementedError()
