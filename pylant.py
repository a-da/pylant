import importlib
import inspect
import types
from pathlib import Path
from typing import Any, Tuple, Set, Dict, Union
from unittest import mock


class Plantuml:
    """
    Draw plant diagram
    """
    START_TAG = "@startuml"
    END_TAG = "@enduml"

    def __init__(self) -> None:
        self._file = Path(__file__).parent / "sequence.plantuml"
        self._file.write_text(self.START_TAG)

    def add_call(self, from_: str, to: str, method_or_attribute: str) -> None:
        message = f"{from_} --> {to}: {method_or_attribute}"

        import time
        time.sleep(0.01)
        content = self._file.read_text()
        assert content
        lines = content.splitlines()

        if self.END_TAG in lines:
            lines = lines[:-1]

        # group and increment the same calls
        if message in lines[-1]:
            parsed = lines[-1].rsplit(" +", maxsplit=1)
            if len(parsed) == 1:
                head, count = parsed[0], "1"
            else:
                head, count = parsed

            lines[-1] = f"{head} +{int(count) + 1}"
        else:
            lines.append(message)

        if self.END_TAG not in lines:
            lines.append(self.END_TAG)

        self._file.write_text("\n".join(lines))


class PlantPatch:
    """
    Patch modules and classes to track each call latter to be included in sequence diagram
    """
    def __init__(self):
        #: map each original api entity by a unique id
        self._original: Dict[str, Union[types.ModuleType, types.FunctionType]] = {}

        self._modules_by_path = {}
        self._uml = Plantuml()
        self._patched_classes: Set[Tuple[types.ModuleType, str]] = set()

    @staticmethod
    def module_to_uniq_map_id(module: types.ModuleType, method_or_attribute_name: str) -> str:
        return f"{module.__name__}.{method_or_attribute_name}"

    def find_the_caller(self, stack_level: int = 5) -> types.ModuleType:
        # keep all operation apart for a debugging purposes
        stack = inspect.stack()
        from_frame = stack[stack_level]
        module_path = from_frame[1]

        count = 0
        while "/lib/python" in module_path:
            stack_level += 1
            from_frame = stack[stack_level]
            module_path = from_frame[1]
            count += 1
            if count > 1000:
                raise NotImplementedError('Infinite loop detected')

        return self._modules_by_path[module_path]

    def locate_all_modules(self, *modules: types.ModuleType, ignore_modules=None):
        all_modules = list(modules)
        for module in modules:
            nest_count = len(module.__name__.split('.'))
            package = Path(module.__file__).parent
            if package.joinpath("__init__.py").exists():
                sub_packages = list(package.glob("./*/__init__.py"))
                for sub_package in sub_packages:
                    import_str = ".".join(str(sub_package.parent).rsplit("/", maxsplit=nest_count + 1)[1:])

                    if import_str in ignore_modules:
                        continue

                    sub_module = importlib.import_module(import_str)
                    all_modules.extend(self.locate_all_modules(sub_module, ignore_modules=ignore_modules))

                    sibling_modules = []
                    for python_file in sub_package.parent.glob("*.py"):
                        # ignore __init__.py
                        if python_file == sub_package:
                            continue

                        import_str = ".".join(str(python_file)[:-3].rsplit("/", maxsplit=nest_count + 2)[1:])

                        if import_str in ignore_modules:
                            continue

                        sibling_modules.append(importlib.import_module(import_str))

                    all_modules.extend(sibling_modules)

        for ignore_module_name in ignore_modules:
            ignore_module = importlib.import_module(ignore_module_name)
            self._modules_by_path[ignore_module.__file__] = ignore_module

        return all_modules

    def patch_modules(self, *modules: types.ModuleType):
        our_modules = {module.__name__ for module in modules}
        for module in modules:
            self._modules_by_path[module.__file__] = module

            for method_or_attribute_name in dir(module):
                # is a constant
                if method_or_attribute_name.upper() == method_or_attribute_name:
                    continue

                # probably is builtin
                if method_or_attribute_name.startswith('__'):
                    continue

                module_item = getattr(module, method_or_attribute_name)

                # leave this for debug
                if hasattr(module_item, '__name__'):
                    entity_name = module_item.__name__
                    if entity_name == 'SomeClassName':
                        debug = 1

                real_module = inspect.getmodule(module_item)

                # check if module item is a class
                if isinstance(module_item, type):
                    # not implemented yet
                    import enum
                    if issubclass(module_item, enum.Enum):
                        continue

                    if issubclass(module_item, (Exception, BaseException)):
                        continue

                    from collections.abc import Hashable
                    if module_item.__base__ is Hashable:
                        continue

                    if module_item.__module__ in our_modules:

                        self.patch_classes(
                            (
                                module,
                                method_or_attribute_name
                            ),
                        )

                    continue

                # check if module item is a class
                if isinstance(module_item, types.FunctionType):
                    uniq_map_id = self.module_to_uniq_map_id(real_module, method_or_attribute_name)

                    self._original[uniq_map_id] = module_item

                    def _wrapper(*args, x_module=real_module,
                                 x_method_or_attribute_name=method_or_attribute_name,
                                 x_uniq_map_id=uniq_map_id,
                                 **kwargs):
                        """
                        x_method_or_attribute_name: method_or_attribute_name_
                        https://stackoverflow.com/questions/3431676/creating-functions-in-a-loop
                        """
                        from_name = self.find_the_caller().__name__

                        self._uml.add_call(from_name, x_module.__name__, x_method_or_attribute_name)

                        return self._original[x_uniq_map_id].__call__(*args, **kwargs)

                    mock.patch.object(module, method_or_attribute_name, side_effect=_wrapper).start()

                    continue

                # Primitives
                if isinstance(module_item, (int, str, float, types.ModuleType, Path)):
                    continue

    def patch_classes(self, *classes: Tuple[types.ModuleType, str]):
        for module_to_patch, class_name in classes:
            if (module_to_patch, class_name) in self._patched_classes:
                continue

            self._patched_classes.add((module_to_patch, class_name))

            assert isinstance(class_name, str)
            # === create dynamic class ===
            # https://www.geeksforgeeks.org/create-classes-dynamically-in-python/
            class_value = getattr(module_to_patch, class_name)

            def __init__(self_, *args, x_class_value: type = class_value, **kwargs) -> None:

                from_name = self.find_the_caller(stack_level=5).__name__
                self._uml.add_call(from_name, x_class_value.__qualname__, '__init__')
                x_class_value.__init__(self_, *args, **kwargs)

            def __getattribute__(self_, name: str, x_class_value: type = class_value) -> Any:
                from_name = self.find_the_caller(stack_level=2).__name__
                self._uml.add_call(from_name, x_class_value.__qualname__, name)

                return object.__getattribute__(self_, name)

            # # creating class dynamically
            if not hasattr(class_value, "__qualname__"):
                continue

            proxy_class_name = f"{class_value.__qualname__}Proxy"
            the_class = type(proxy_class_name, (class_value, object), {
                "__init__": __init__,
                "__getattribute__": __getattribute__
            })

            mock.patch.object(module_to_patch, class_name, side_effect=the_class).start()
