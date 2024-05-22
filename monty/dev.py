"""
This module implements several useful functions and decorators that can be
particularly useful for developers. E.g., deprecating methods / classes, etc.
"""

from __future__ import annotations

import functools
import inspect
import logging
import os
import subprocess
import sys
import warnings
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Callable, Optional, Type

logger = logging.getLogger(__name__)


def deprecated(
    replacement: Optional[Callable] = None,
    message: str = "",
    deadline: Optional[tuple[int, int, int]] = None,
    category: Type[Warning] = FutureWarning,
) -> Callable:
    """
    Decorator to mark classes or functions as deprecated, with a possible replacement.

    Args:
        replacement (callable): A replacement class or method.
        message (str): A warning message to be displayed.
        deadline (Optional[tuple[int, int, int]]): Optional deadline for removal
            of the old function/class, in format (yyyy, MM, dd). A CI warning would
            be raised after this date if is running in code owner' repo.
        category (Warning): Choose the category of the warning to issue. Defaults
            to FutureWarning. Another choice can be DeprecationWarning. Note that
            FutureWarning is meant for end users and is always shown unless silenced.
            DeprecationWarning is meant for developers and is never shown unless
            python is run in developmental mode or the filter is changed. Make
            the choice accordingly.

    Returns:
        Original function, but with a warning to use the updated class.
    """

    def raise_deadline_warning() -> None:
        """Raise CI warning after removal deadline in code owner's repo."""

        def _is_in_owner_repo() -> bool:
            """Check if is running in code owner's repo.
            Only generate reliable check when `git` is installed and remote name
            is "origin".
            """

            try:
                # Get current running repo
                result = subprocess.run(
                    ["git", "config", "--get", "remote.origin.url"],
                    stdout=subprocess.PIPE,
                )
                owner_repo = (
                    result.stdout.decode("utf-8")
                    .strip()
                    .lstrip("https://github.com/")  # HTTPS clone
                    .lstrip("git@github.com:")  # SSH clone
                    .rstrip(".git")  # SSH clone
                )

                return owner_repo == os.getenv("GITHUB_REPOSITORY")

            except (subprocess.CalledProcessError, FileNotFoundError):
                return False

        # Only raise warning in code owner's repo CI
        if (
            _deadline is not None
            and os.getenv("CI") is not None
            and datetime.now() > _deadline
            and _is_in_owner_repo()
        ):
            raise DeprecationWarning(
                f"This function should have been removed on {_deadline:%Y-%m-%d}."
            )

    def craft_message(
        old: Callable,
        replacement: Callable,
        message: str,
        deadline: datetime,
    ) -> str:
        msg = f"{old.__name__} is deprecated"

        if deadline is not None:
            msg += f", and will be removed on {_deadline:%Y-%m-%d}\n"

        if replacement is not None:
            if isinstance(replacement, property):
                r = replacement.fget
            elif isinstance(replacement, (classmethod, staticmethod)):
                r = replacement.__func__
            else:
                r = replacement

            if deadline is None:
                msg += "; use "  # for better formatting
            else:
                msg += "Use "
            msg += f"{r.__name__} in {r.__module__} instead."

        if message:
            msg += "\n" + message
        return msg

    def deprecated_function_decorator(old: Callable) -> Callable:
        def wrapped(*args, **kwargs):
            msg = craft_message(old, replacement, message, _deadline)
            warnings.warn(msg, category=category, stacklevel=2)
            return old(*args, **kwargs)

        return wrapped

    def deprecated_class_decorator(cls: Type) -> Type:
        original_init = cls.__init__

        def new_init(self, *args, **kwargs):
            msg = craft_message(cls, replacement, message, _deadline)
            warnings.warn(msg, category=category, stacklevel=2)
            original_init(self, *args, **kwargs)

        cls.__init__ = new_init
        return cls

    # Convert deadline to datetime type
    _deadline = datetime(*deadline) if deadline is not None else None

    # Raise CI warning after removal deadline
    raise_deadline_warning()

    def decorator(target: Callable) -> Callable:
        if inspect.isfunction(target):
            return deprecated_function_decorator(target)
        elif inspect.isclass(target):
            return deprecated_class_decorator(target)
        else:
            raise TypeError(
                "The @deprecated decorator can only be applied to classes or functions"
            )

    return decorator


class requires:
    """
    Decorator to mark classes or functions as requiring a specified condition
    to be true. This can be used to present useful error messages for
    optional dependencies. For example, decorating the following code will
    check if scipy is present and if not, a runtime error will be raised if
    someone attempts to call the use_scipy function:

        try:
            import scipy
        except ImportError:
            scipy = None

        @requires(scipy is not None, "scipy is not present.")
        def use_scipy():
            print(scipy.majver)

    Args:
        condition: Condition necessary to use the class or function.
        message: A message to be displayed if the condition is not True.
    """

    def __init__(
        self, condition: bool, message: str, err_cls: type[Exception] = RuntimeError
    ) -> None:
        """
        Args:
            condition: A expression returning a bool.
            message: Message to display if condition is False.
        """
        self.condition = condition
        self.message = message
        self.err_cls = err_cls

    def __call__(self, _callable: Callable) -> Callable:
        """
        Args:
            _callable: Callable function.
        """

        @functools.wraps(_callable)
        def decorated(*args, **kwargs):
            if not self.condition:
                raise self.err_cls(self.message)
            return _callable(*args, **kwargs)

        return decorated


def install_excepthook(hook_type: str = "color", **kwargs) -> int:
    """
    This function replaces the original python traceback with an improved
    version from Ipython. Use `color` for colourful traceback formatting,
    `verbose` for Ka-Ping Yee's "cgitb.py" version kwargs are the keyword
    arguments passed to the constructor. See IPython.core.ultratb.py for more
    info.

    Returns:
        0 if hook is installed successfully.
    """
    try:
        from IPython.core import ultratb  # pylint: disable=import-outside-toplevel
    except ImportError:
        warnings.warn("Cannot install excepthook, IPyhon.core.ultratb not available")
        return 1

    # Select the hook.
    hook = dict(
        color=ultratb.ColorTB,
        verbose=ultratb.VerboseTB,
    ).get(hook_type.lower(), None)

    if hook is None:
        return 2

    sys.excepthook = hook(**kwargs)
    return 0
