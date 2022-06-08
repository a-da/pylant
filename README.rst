The motivation
==============

1. Get overview of the entire design picture of the system.
2. Spot weak points in the design.
3. Have autogenerate up to date interaction design per workflow.

The solution
============

1. Patch interested classes to be tracked (register each method call).
2. Run a notebook implementation of interested workflow.
3. Draw a sequential diagram based on calls caught from patch and run.
4. Read/Interpret the diagram.

Details
=======

Patch
+++++

1. patch_modules

.. code-block:: python

    # a.py
    def foo():
        return 'foo'

    # pylant.py
    ...
    class PlantPatch:
        ...
        def patch_modules(self, *modules: types.ModuleType):
            ...
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

    import a
    modules = plant.locate_all_modules(a, ...)
    p.patch_modules(modules)


2. patch_class

.. code-block:: python

    # a.py
    class A:
        def __init__(self):
            self._a = a()
        def bar(self):
            return 'bar'

    # pylant.py
    ...
    class PlantPatch:
        ...
        def patch_classes(self, *classes: Tuple[types.ModuleType, str]):
            for module_to_patch, class_name in classes:
                ...
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


                if not hasattr(class_value, "__qualname__"):
                    continue

                # # creating class dynamically
                proxy_class_name = f"{class_value.__qualname__}Proxy"
                the_class = type(proxy_class_name, (class_value, object), {
                    "__init__": __init__,
                    "__getattribute__": __getattribute__
                })

                mock.patch.object(module_to_patch, class_name, side_effect=the_class).start()


3. patch workflow

.. code-block:: python

    def patch() -> None:
        plant = PlantPatch()

        import a
        import a_pay
        import a_common
        main_import = __import__(__name__)

        modules = plant.locate_all_modules(
            main_import,
            a,
            a_pay,
            a_common,
            ignore_modules=[
                'a_pay.process_setup',

                'a.core.sum.a.b',  # don't know why is failing
                'a.core.sum.a.a_entity',  # don't know why is failing
                'a.core.sum.builder.grouper',
            ]
        )
        plant.patch_modules(*modules)

    def main():
        print('======================')
        print('starting the real app')
        print('======================')

        patch()

        ...
        the_workflow_method(task)

        now = datetime.now()
        current_time = now.strftime("%H:%M:%S")
        print("End Time =", current_time)

4. draw uml diagram

    Lots of example here https://plantuml.com/sequence-diagram.

    Plugin in IDE PlantUml.

    Command Line in makefile.

TO be done
==========

1. Declaring participant Database, Http, notebook ...
2. Custom profiling: timing, CPU and RAM usage.
3. Construct Class Diagram out of **captures** sequence diagram.
4. Integrate diagram in <git_repo>/docs. Generate new documentation with new release.

Setup
=====

.. code-block::

    brew install plantuml
    plantuml ./a/b/calc2.py
    $ ls ./a/b/calc2*
    ./a/b/calc2.png
    ./a/b/calc2.py
