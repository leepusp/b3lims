"""Private ELN drafts with immutable revisions.

No central database writes.

The caller must authorize ELN access and resolve the Django
user from the authenticated request. The physical destination
remains governed by UserHomeLabToolsStorage and its broker.
"""

from __future__ import annotations

import json
import re

from datetime import datetime, timezone
from uuid import UUID, uuid4

from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile

from core.services.lab_tools_storage import (
    UserHomeLabToolsStorage,
)


PROJECT_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$"
)

USERNAME_RE = re.compile(
    r"^[a-z_][a-z0-9_-]{0,31}$"
)

REVISION_RE = re.compile(
    r"^r([0-9]{6})\.json$"
)

SCHEMA_VERSION = 1
MAX_TEXT_LENGTH = 200_000
MAX_LINKS = 100


class DraftValidationError(ValueError):
    pass


class DraftConflict(RuntimeError):
    pass


class DraftNotFound(LookupError):
    pass


def _owner(user):
    if (
        user is None
        or not getattr(user, "is_authenticated", False)
        or not getattr(user, "is_active", False)
    ):
        raise PermissionDenied(
            "An authenticated, active owner is required."
        )

    username = str(user.get_username())

    if not USERNAME_RE.fullmatch(username):
        raise DraftValidationError(
            "Invalid Unix account name."
        )

    return username


def _project(value):
    if not isinstance(value, str):
        raise DraftValidationError(
            "Project name must be a string."
        )

    if not PROJECT_RE.fullmatch(value) or ".." in value:
        raise DraftValidationError(
            "Invalid project directory name."
        )

    return value


def _entry_id(value):
    if not isinstance(value, str):
        raise DraftValidationError(
            "Invalid entry identifier."
        )

    try:
        parsed = UUID(value)
    except (ValueError, TypeError) as exc:
        raise DraftValidationError(
            "Invalid entry identifier."
        ) from exc

    if parsed.version != 4 or str(parsed) != value:
        raise DraftValidationError(
            "Entry identifier must be a canonical UUID4."
        )

    return value


def _text(value, *, required=False, limit=MAX_TEXT_LENGTH):
    if not isinstance(value, str):
        raise DraftValidationError(
            "ELN content must be textual."
        )

    if len(value) > limit:
        raise DraftValidationError(
            "ELN content exceeds the permitted length."
        )

    if required and not value.strip():
        raise DraftValidationError(
            "A title is required."
        )

    return value


def _ids(values):
    if not isinstance(values, (list, tuple)):
        raise DraftValidationError(
            "Material references must be a list."
        )

    if len(values) > MAX_LINKS:
        raise DraftValidationError(
            "Too many linked materials."
        )

    result = []

    for value in values:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
        ):
            raise DraftValidationError(
                "Invalid material identifier."
            )

        if value not in result:
            result.append(value)

    return result


def logical_revision_path(
    username,
    project,
    entry_id,
    revision,
):
    if not USERNAME_RE.fullmatch(username):
        raise DraftValidationError("Invalid username.")

    project = _project(project)
    entry_id = _entry_id(entry_id)

    if (
        isinstance(revision, bool)
        or not isinstance(revision, int)
        or not 1 <= revision <= 999999
    ):
        raise DraftValidationError(
            "Invalid revision number."
        )

    return (
        f"users/{username}/eln/projects/{project}/"
        f"entries/{entry_id}/revisions/"
        f"r{revision:06d}.json"
    )


class PrivateDraftRepository:
    """Owner-scoped, immutable private draft repository."""

    def __init__(self, storage=None):
        self.storage = (
            storage
            if storage is not None
            else UserHomeLabToolsStorage()
        )

    @staticmethod
    def _entry_root(username, project, entry_id):
        return (
            f"users/{username}/eln/projects/"
            f"{project}/entries/{entry_id}"
        )

    def _revisions(self, username, project, entry_id):
        root = self._entry_root(
            username, project, entry_id
        ) + "/revisions"

        try:
            _directories, files = self.storage.listdir(
                root
            )
        except FileNotFoundError:
            return []

        revisions = []

        for filename in files:
            match = REVISION_RE.fullmatch(filename)

            if match:
                revision = int(match.group(1))

                if revision >= 1:
                    revisions.append(revision)

        return sorted(set(revisions))

    def read_revision(
        self, user, project, entry_id, revision
    ):
        username = _owner(user)
        project = _project(project)
        entry_id = _entry_id(entry_id)

        name = logical_revision_path(
            username, project, entry_id, revision
        )

        try:
            with self.storage._open(name, "rb") as stream:
                payload = json.load(stream)
        except FileNotFoundError as exc:
            raise DraftNotFound(
                "ELN revision not found."
            ) from exc

        if not isinstance(payload, dict):
            raise DraftValidationError(
                "Invalid ELN revision document."
            )

        expected = {
            "schema_version": SCHEMA_VERSION,
            "owner": username,
            "project": project,
            "entry_id": entry_id,
            "revision": revision,
        }

        for key, value in expected.items():
            if payload.get(key) != value:
                raise DraftValidationError(
                    "ELN revision integrity mismatch."
                )

        return payload

    def latest(self, user, project, entry_id):
        username = _owner(user)
        project = _project(project)
        entry_id = _entry_id(entry_id)

        revisions = self._revisions(
            username, project, entry_id
        )

        if not revisions:
            raise DraftNotFound(
                "Private ELN entry not found."
            )

        return self.read_revision(
            user,
            project,
            entry_id,
            revisions[-1],
        )

    def _write(
        self,
        user,
        project,
        entry_id,
        revision,
        *,
        title,
        content,
        protocol,
        results,
        sample_ids,
        chemical_ids,
        material_authorizer,
    ):
        username = _owner(user)
        project = _project(project)
        entry_id = _entry_id(entry_id)

        title = _text(
            title, required=True, limit=300
        ).strip()

        content = _text(content)
        protocol = _text(protocol)
        results = _text(results)

        samples = _ids(sample_ids)
        chemicals = _ids(chemical_ids)

        # Material links must never be accepted without
        # an explicit access validator.
        if samples or chemicals:
            if material_authorizer is None:
                raise DraftValidationError(
                    "Material access validation is required."
                )

        if material_authorizer is not None:
            if not material_authorizer(
                user, samples, chemicals
            ):
                raise PermissionDenied(
                    "Linked materials are not accessible."
                )

        document = {
            "schema_version": SCHEMA_VERSION,
            "entry_id": entry_id,
            "revision": revision,
            "owner": username,
            "project": project,
            "status": "draft",
            "title": title,
            "content": content,
            "protocol": protocol,
            "results": results,
            "sample_ids": samples,
            "chemical_ids": chemicals,
            "saved_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }

        name = logical_revision_path(
            username, project, entry_id, revision
        )

        data = json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ).encode("utf-8")

        # The protected backend uses O_EXCL. Calling its
        # _save directly preserves the immutable filename
        # instead of asking Django to generate a new one.
        written = self.storage._save(
            name,
            ContentFile(data),
        )

        if written != name:
            raise DraftConflict(
                "Storage returned an unexpected path."
            )

        return document

    def create(
        self,
        user,
        project,
        *,
        title,
        content="",
        protocol="",
        results="",
        sample_ids=(),
        chemical_ids=(),
        material_authorizer=None,
    ):
        username = _owner(user)
        project = _project(project)

        return self._write(
            user,
            project,
            str(uuid4()),
            1,
            title=title,
            content=content,
            protocol=protocol,
            results=results,
            sample_ids=sample_ids,
            chemical_ids=chemical_ids,
            material_authorizer=material_authorizer,
        )

    def revise(
        self,
        user,
        project,
        entry_id,
        *,
        expected_revision,
        title,
        content="",
        protocol="",
        results="",
        sample_ids=(),
        chemical_ids=(),
        material_authorizer=None,
    ):
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
        ):
            raise DraftValidationError(
                "Invalid expected revision."
            )

        latest = self.latest(
            user, project, entry_id
        )

        if latest["revision"] != expected_revision:
            raise DraftConflict(
                "The ELN entry has a newer revision."
            )

        if expected_revision >= 999999:
            raise DraftConflict(
                "Revision limit reached."
            )

        return self._write(
            user,
            project,
            entry_id,
            expected_revision + 1,
            title=title,
            content=content,
            protocol=protocol,
            results=results,
            sample_ids=sample_ids,
            chemical_ids=chemical_ids,
            material_authorizer=material_authorizer,
        )

    def list_entries(self, user, project):
        username = _owner(user)
        project = _project(project)

        root = (
            f"users/{username}/eln/projects/"
            f"{project}/entries"
        )

        try:
            directories, _files = self.storage.listdir(
                root
            )
        except FileNotFoundError:
            return []

        if len(directories) > 10000:
            raise DraftValidationError(
                "Project entry count exceeds listing limit."
            )

        entries = []

        for candidate in directories:
            try:
                entry_id = _entry_id(candidate)
            except DraftValidationError:
                continue

            try:
                entries.append(
                    self.latest(
                        user, project, entry_id
                    )
                )
            except DraftNotFound:
                continue

        return sorted(
            entries,
            key=lambda value: value["saved_at"],
            reverse=True,
        )
