# -*- coding: utf-8 -*-

import sqlite3

from plexpy import database
from plexpy import helpers


ENTITY_ITEM = 'item'
ENTITY_USER = 'user'
ENTITY_LIBRARY = 'library'
ENTITY_COLLECTION = 'collection'
ENTITY_PLAYLIST = 'playlist'
ENTITY_DEVICE = 'device'
ENTITY_TYPES = frozenset({
    ENTITY_ITEM, ENTITY_USER, ENTITY_LIBRARY, ENTITY_COLLECTION, ENTITY_PLAYLIST, ENTITY_DEVICE,
})


class IdentityMappingError(ValueError):
    pass


class IdentityMappingExhaustedError(IdentityMappingError):
    pass


class ExternalIdMapper:
    """Map backend-native string identities to globally unique numeric IDs."""

    def __init__(self, backend, server_id, database_file=None):
        self.backend = self._required_identity('backend', backend).strip().lower()
        self.server_id = self._required_identity('server_id', server_id)
        self.database_file = database.db_filename(database_file)

    @staticmethod
    def _required_identity(name, value):
        if value is None:
            raise IdentityMappingError('{} cannot be empty'.format(name))
        value = str(value)
        if not value.strip():
            raise IdentityMappingError('{} cannot be empty'.format(name))
        return value

    @staticmethod
    def _entity_type(entity_type):
        entity_type = str(entity_type).lower() if entity_type is not None else ''
        if entity_type not in ENTITY_TYPES:
            raise IdentityMappingError('Unsupported entity type: {!r}'.format(entity_type))
        return entity_type

    def _external_id(self, external_id):
        return self._required_identity('external_id', external_id)

    def to_local(self, entity_type, external_id):
        entity_type = self._entity_type(entity_type)
        external_id = self._external_id(external_id)
        connection = sqlite3.connect(self.database_file, timeout=20)
        try:
            row = connection.execute(
                "SELECT local_id FROM external_id_map WHERE backend = ? AND server_id = ? "
                "AND entity_type = ? AND external_id = ?",
                [self.backend, self.server_id, entity_type, external_id]
            ).fetchone()
            return int(row[0]) if row else None
        finally:
            connection.close()

    def to_external(self, entity_type, local_id):
        entity_type = self._entity_type(entity_type)
        try:
            local_id = int(local_id)
        except (TypeError, ValueError):
            raise IdentityMappingError('local_id must be a positive integer')
        if local_id <= 0:
            raise IdentityMappingError('local_id must be a positive integer')
        connection = sqlite3.connect(self.database_file, timeout=20)
        try:
            row = connection.execute(
                "SELECT external_id FROM external_id_map WHERE backend = ? AND server_id = ? "
                "AND entity_type = ? AND local_id = ?",
                [self.backend, self.server_id, entity_type, local_id]
            ).fetchone()
            return row[0] if row else None
        finally:
            connection.close()

    def get_or_create(self, entity_type, external_id):
        entity_type = self._entity_type(entity_type)
        external_id = self._external_id(external_id)
        existing = self.to_local(entity_type, external_id)
        if existing is not None:
            return existing

        with database.db_lock:
            connection = sqlite3.connect(self.database_file, timeout=20, isolation_level=None)
            try:
                connection.execute('BEGIN IMMEDIATE')
                row = connection.execute(
                    "SELECT local_id FROM external_id_map WHERE backend = ? AND server_id = ? "
                    "AND entity_type = ? AND external_id = ?",
                    [self.backend, self.server_id, entity_type, external_id]
                ).fetchone()
                if row:
                    connection.commit()
                    return int(row[0])

                counter = connection.execute(
                    "SELECT value FROM version_info WHERE key = ?",
                    [database.EXTERNAL_ID_COUNTER_KEY]
                ).fetchone()
                if not counter:
                    next_id = database.reseed_external_id_counter(connection=connection)
                else:
                    try:
                        next_id = int(counter[0])
                    except (TypeError, ValueError):
                        next_id = database.reseed_external_id_counter(connection=connection)
                if next_id > database.MAX_SAFE_INTEGER:
                    raise IdentityMappingExhaustedError('External ID namespace is exhausted')

                now = helpers.timestamp()
                connection.execute(
                    "INSERT INTO external_id_map "
                    "(backend, server_id, entity_type, external_id, local_id, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [self.backend, self.server_id, entity_type, external_id, next_id, now, now]
                )
                connection.execute(
                    "INSERT OR REPLACE INTO version_info (key, value) VALUES (?, ?)",
                    [database.EXTERNAL_ID_COUNTER_KEY, str(next_id + 1)]
                )
                connection.commit()
                return next_id
            except IdentityMappingError:
                connection.rollback()
                raise
            except sqlite3.Error as error:
                connection.rollback()
                raise IdentityMappingError('Unable to persist external identity mapping') from error
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()
