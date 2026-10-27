"""Coordinated release switch with paired-link rollback.

This module has no deployment CLI or service operations.
Service quiescence, restart and health verification are
explicitly supplied by the caller.
"""

import os
import re
import secrets
from pathlib import Path


class CutoverRolledBack(RuntimeError):
    """Cutover failed, and both previous links were restored."""


class RollbackIncomplete(RuntimeError):
    """The previous operational state could not be proven."""


class CoordinatedReleaseTransaction:
    def __init__(
        self,
        app_root,
        active_commit,
        target_commit,
        quiesce,
        restart,
        verify,
    ):
        self.root = Path(app_root)
        self.active = active_commit
        self.target = target_commit
        self.quiesce = quiesce
        self.restart = restart
        self.verify = verify

        self.current = self.root / "current"
        self.static = self.root / "static-current"

    @staticmethod
    def _validate_commit(value):
        return isinstance(value, str) and bool(
            re.fullmatch(r"[0-9a-f]{40}", value)
        )

    def _expected_link(self, kind, commit):
        # Preserve the link representation already in use.
        # Existing deployments may use absolute targets;
        # isolated transaction tests use relative targets.
        if (
            self.current.is_symlink()
            and os.path.isabs(os.readlink(self.current))
        ):
            return str(self.root / kind / commit)
        return f"{kind}/{commit}"

    def _assert_links(self, commit):
        expected = (
            (
                self.current,
                self._expected_link("releases", commit),
            ),
            (
                self.static,
                self._expected_link("static-releases", commit),
            ),
        )

        for link, target in expected:
            if not link.is_symlink():
                raise RuntimeError(
                    f"Required release link missing: {link.name}"
                )

            if os.readlink(link) != target:
                raise RuntimeError(
                    f"Unexpected release link: {link.name}"
                )

    def _preflight(self):
        if not self._validate_commit(self.active):
            raise RuntimeError("Invalid active release ID")

        if not self._validate_commit(self.target):
            raise RuntimeError("Invalid target release ID")

        if self.active == self.target:
            raise RuntimeError("Target already active")

        self._assert_links(self.active)

        for directory in (
            self.root / "releases" / self.active,
            self.root / "static-releases" / self.active,
            self.root / "releases" / self.target,
            self.root / "static-releases" / self.target,
        ):
            if not directory.is_dir():
                raise RuntimeError(
                    f"Release directory missing: {directory}"
                )

    @staticmethod
    def _replace_symlink(link, destination):
        temporary = link.with_name(
            f".{link.name}.switch.{secrets.token_hex(8)}"
        )

        try:
            os.symlink(destination, temporary)
            os.replace(temporary, link)
        finally:
            temporary.unlink(missing_ok=True)

    def _set_links(self, commit):
        self._replace_symlink(
            self.current,
            self._expected_link("releases", commit),
        )

        self._replace_symlink(
            self.static,
            self._expected_link("static-releases", commit),
        )

        self._assert_links(commit)

    def execute(self):
        self._preflight()

        recovery_required = False

        try:
            # The caller must also block external HTTP access
            # if it requires a fully quiescent cutover.
            recovery_required = True
            self.quiesce()

            self._set_links(self.target)

            self.restart()
            self._assert_links(self.target)
            self.verify(self.target)

            return self.target

        except Exception as original_error:
            if not recovery_required:
                raise

            try:
                self._set_links(self.active)
                self.restart()
                self._assert_links(self.active)
                self.verify(self.active)

            except Exception as rollback_error:
                raise RollbackIncomplete(
                    "Previous release could not be "
                    "fully restored and verified"
                ) from rollback_error

            raise CutoverRolledBack(
                "Cutover failed; previous release restored"
            ) from original_error
