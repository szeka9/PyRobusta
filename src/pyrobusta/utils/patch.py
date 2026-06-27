"""
Helper methods for patching classes
"""

# pylint: disable=W0212


def add_method(cls, func: callable, method_type="instance"):
    """
    Helper to patch/extend classes with additional methods and states.
    :param func: function to add
    :param method_type: type of the method (instance, static, class)
    """
    if method_type == "instance":
        setattr(cls, func.__name__, func)
    elif method_type == "static":
        setattr(cls, func.__name__, staticmethod(func))
    elif method_type == "class":
        setattr(cls, func.__name__, classmethod(func))
    else:
        raise ValueError("Invalid type")


def add_property(cls, getter: callable, setter: callable = None):
    """
    Add a property to a class.
    """
    setattr(cls, getter.__name__, property(getter, setter))


def patch_extra_property(cls, name):
    """
    Add a property to 'cls' that stores its value in the instance's
    '_extras' dictionary. Intended for '__slots__' classes that cannot
    have arbitrary instance attributes.
    """

    def getter(self):
        return self._extras.get(name) if self._extras else None

    def setter(self, value):
        if self._extras is None:
            self._extras = {}
        self._extras[name] = value

    setattr(cls, name, property(getter, setter))
