"""
plant uml + python -> pylant.py
"""
from typing import Any, Tuple, Set, Dict, Union, List, cast

import enum
import importlib
import inspect
import types
from collections.abc import Hashable
from pathlib import Path
from unittest import mock


class Plantuml:
    """
    Draw plant diagram
    """
    START_TAG = "@startuml"
    END_TAG = "@enduml"

    def __init__(self, store_directory: Path) -> None:
        self._file = store_directory / "sequence.plantuml"
        self._content = [self.START_TAG]

    def save(self) -> None:
        """Dump all calls into a plant uml file"""
        print(f'Save calls to {self._file}')
        self._file.write_text("\n".join(self._content + [self.END_TAG]))

    def add_call(self, from_: str, to: str, method_or_attribute: str) -> None:  # pylint: disable=invalid-name
        """
        Collect call to draw a sequence diagram later
        """
        message = f"{from_} --> {to}: {method_or_attribute}"

        # group and increment the same calls
        last = self._content[-1]
        if message in last:
            parsed = last.rsplit(" +", maxsplit=1)
            if len(parsed) == 1:
                head, count = parsed[0], "1"
            else:
                head, count = parsed

            self._content[-1] = f"{head} +{int(count) + 1}"
        else:
            self._content.append(message)


class PlantPatch:
    """
    Patch modules and classes to track each call latter to be included in sequence diagram
    """
    def __init__(self, store_directory: Path) -> None:
        #: map each original api entity by a unique id
        self._original: Dict[str, Union[types.ModuleType, types.FunctionType]] = {}

        self._modules_by_path: Dict[str, types.ModuleType] = {}
        self._uml = Plantuml(store_directory)
        self._patched_classes: Set[Tuple[types.ModuleType, str]] = set()

    @staticmethod
    def module_to_uniq_map_id(module: types.ModuleType, method_or_attribute_name: str) -> str:
        """
        Convert module and method_or_attribute_name into a unique map id
        """
        return f"{module.__name__}.{method_or_attribute_name}"

    def find_the_caller(self, stack_level: int = 5) -> types.ModuleType:
        """
        Find who call the current function
        """
        # keep all operation apart for a debugging purposes
        stack = inspect.stack()
        from_frame = stack[stack_level]
        module_path = from_frame[1]

        count = 0
        while module_path not in self._modules_by_path:
            stack_level += 1
            from_frame = stack[stack_level]
            module_path = from_frame[1]
            count += 1
            if count > 1000:
                raise NotImplementedError('Infinite loop detected')

        return self._modules_by_path[module_path]

    @staticmethod
    def _locate_simpling_module(module: Path, nest_count: int, ignore_modules: List):
        siblings = []
        for python_file in module.glob("*.py"):
            # ignore __init__.py
            if str(python_file).endswith('__init__.py'):
                continue

            pack = str(python_file)[:-3].rsplit("/", maxsplit=nest_count + 2)
            import_str = ".".join(pack[1:])

            if import_str in ignore_modules:
                continue

            siblings.append(importlib.import_module(import_str))
        return siblings


    def locate_all_modules(self, *modules: types.ModuleType,  # pylint: disable=too-many-locals
                           ignore_modules: List[str]) -> List[types.ModuleType]:
        """Search recursive for the all modules"""
        all_modules = list(modules)
        for module in modules:
            nest_count = len(module.__name__.split('.'))
            path = cast(str, module.__file__)
            package = Path(path).parent
            if package.joinpath("__init__.py").exists():
                sub_packages = list(package.glob("./*/__init__.py"))
                for sub_package in sub_packages:
                    pack = str(sub_package.parent).rsplit("/", maxsplit=nest_count + 1)
                    import_str = ".".join(pack[1:])

                    if import_str in ignore_modules:
                        continue

                    sub_module = importlib.import_module(import_str)
                    all_modules.extend(
                        self.locate_all_modules(sub_module, ignore_modules=ignore_modules)
                    )

                    sibling_modules = self._locate_simpling_module(sub_package.parent, nest_count, ignore_modules)
                    all_modules.extend(sibling_modules)

                sibling_modules = self._locate_simpling_module(package, nest_count - 1, ignore_modules)
                all_modules.extend(sibling_modules)

        for ignore_module_name in ignore_modules:
            ignore_module = importlib.import_module(ignore_module_name)
            path = cast(str, ignore_module.__file__)
            self._modules_by_path[path] = ignore_module

        return all_modules

    def _patch_functions(self,
                         module: types.ModuleType,
                         real_module: types.ModuleType,
                         function: types.FunctionType,
                         name: str) -> None:
        # check if module item is a function

        uniq_map_id = self.module_to_uniq_map_id(real_module, name)

        self._original[uniq_map_id] = function

        def _wrapper(*args: Any,
                     x_module: types.ModuleType = real_module,
                     x_method_or_attribute_name: str = name,
                     x_uniq_map_id: str = uniq_map_id,
                     **kwargs: Any) -> Any:
            """
            x_method_or_attribute_name: method_or_attribute_name_
            https://stackoverflow.com/questions/3431676/creating-functions-in-a-loop
            """
            assert x_module

            from_name = self.find_the_caller().__name__

            self._uml.add_call(from_name, x_module.__name__, x_method_or_attribute_name)

            return self._original[x_uniq_map_id].__call__(*args, **kwargs)

        mock.patch.object(module, name, side_effect=_wrapper).start()

    def patch_modules(self, *modules: types.ModuleType) -> None:  # pylint: disable=too-many-branches
        """
        From the modules find classes and function and patch them
        """
        our_modules = {module.__name__ for module in modules}
        for module in modules:
            path = cast(str, module.__file__)
            self._modules_by_path[path] = module

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
                        debug = 1  # pylint: disable=unused-variable

                real_module = cast(types.ModuleType, inspect.getmodule(module_item))

                # check if module item is a class
                if isinstance(module_item, type):
                    # not implemented yet

                    if issubclass(module_item, enum.Enum):
                        continue

                    if issubclass(module_item, (Exception, BaseException)):
                        continue

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

                # check if module item is a function
                if isinstance(module_item, types.FunctionType):
                    self._patch_functions(
                        module=module,
                        real_module=real_module,
                        function=module_item,
                        name=method_or_attribute_name)

                    continue

                # Primitives
                if isinstance(module_item, (int, str, float, types.ModuleType, Path)):
                    continue

    def patch_classes(self, *classes: Tuple[types.ModuleType, str]) -> None:
        """
        Patch provided classes:

        1. wrap init
        2. add __getattribute__ method
        """
        for module_to_patch, class_name in classes:
            if (module_to_patch, class_name) in self._patched_classes:
                continue

            self._patched_classes.add((module_to_patch, class_name))

            assert isinstance(class_name, str)
            # === create dynamic class ===
            # https://www.geeksforgeeks.org/create-classes-dynamically-in-python/
            class_value = getattr(module_to_patch, class_name)

            def __init__(self_: Any, *args: Any,
                         x_class_value: type = class_value,
                         **kwargs: Any) -> None:

                from_name = self.find_the_caller(stack_level=5).__name__
                self._uml.add_call(from_name, x_class_value.__qualname__, '__init__')
                x_class_value.__init__(self_, *args, **kwargs)  # type: ignore[misc]

            def __getattribute__(self_: Any, name: str, x_class_value: type = class_value) -> Any:
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

            if 'Rule' in proxy_class_name:
                debug = 1
                # a = the_class(name='a', selector='xpath', type_list_=['+1'])
                # the_class.from_list([])
                # mock.patch.object(module_to_patch, class_name,
                #                   spec=True,
                #                   # new_callable=the_class,
                #                   side_effect=the_class
                #                   ).start()
                # import ciur.shortcuts
                # ciur.shortcuts.Rule = the_class
                # ciur.shortcuts.Rule.from_list([])

            setattr(module_to_patch, class_name, the_class)
            # mock.patch.object(module_to_patch, class_name, side_effect=the_class).start()

    def save(self) -> None:
        """Dump all calls into a plant uml file"""
        self._uml.save()
