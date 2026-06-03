"""SQLite persistence for the AgroLedger MVP application."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import fields
from decimal import Decimal
from pathlib import Path
from typing import Any, TypeVar

from agropekepe.models import (
    CrisisEvent,
    CropSeason,
    DebtAccount,
    Farmer,
    FirstSaleRecord,
    Parcel,
    RemoteSensingObservation,
)

T = TypeVar("T")


class AgroRepository:
    """Dependency-free repository suitable for local development and tests."""

    def __init__(self, database_path: str | Path = ":memory:") -> None:
        self.database_path = str(database_path)
        self.connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

    def close(self) -> None:
        """Close the database connection."""

        self.connection.close()

    def initialize(self) -> None:
        """Create all application tables."""

        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS farmers (
                farmer_id TEXT PRIMARY KEY,
                tax_identifier TEXT NOT NULL UNIQUE,
                legal_name TEXT NOT NULL,
                farmer_type TEXT NOT NULL,
                active_farmer INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS parcels (
                parcel_id TEXT PRIMARY KEY,
                farmer_id TEXT NOT NULL REFERENCES farmers(farmer_id),
                cadastral_reference TEXT NOT NULL,
                right_type TEXT NOT NULL,
                declared_area_ha TEXT NOT NULL,
                measured_area_ha TEXT NOT NULL,
                eligible_area_ha TEXT NOT NULL,
                centroid_lat TEXT NOT NULL,
                centroid_lon TEXT NOT NULL,
                geometry_geojson TEXT NOT NULL,
                public_land_conflict INTEGER NOT NULL,
                protected_area_conflict INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS crop_seasons (
                crop_season_id TEXT PRIMARY KEY,
                parcel_id TEXT NOT NULL REFERENCES parcels(parcel_id),
                farmer_id TEXT NOT NULL REFERENCES farmers(farmer_id),
                claim_year INTEGER NOT NULL,
                production_type TEXT NOT NULL,
                labelled_area_ha TEXT NOT NULL,
                organic INTEGER NOT NULL,
                soil_cover INTEGER NOT NULL,
                irrigation_status TEXT NOT NULL,
                declared_yield_tonnes TEXT,
                verified_yield_tonnes TEXT,
                crop_label_confidence TEXT,
                UNIQUE(parcel_id, farmer_id, claim_year, production_type)
            );
            CREATE TABLE IF NOT EXISTS remote_sensing_observations (
                observation_id TEXT PRIMARY KEY,
                parcel_id TEXT NOT NULL REFERENCES parcels(parcel_id),
                claim_year INTEGER NOT NULL,
                provider TEXT NOT NULL,
                observation_type TEXT NOT NULL,
                confidence TEXT NOT NULL,
                result TEXT NOT NULL,
                evidence_uri TEXT
            );
            CREATE TABLE IF NOT EXISTS first_sale_records (
                first_sale_id TEXT PRIMARY KEY,
                crop_season_id TEXT NOT NULL REFERENCES crop_seasons(crop_season_id),
                invoice_number TEXT NOT NULL,
                buyer_tax_identifier TEXT NOT NULL,
                sale_date TEXT NOT NULL,
                product_type TEXT NOT NULL,
                quantity_tonnes TEXT NOT NULL,
                unit_price_eur TEXT NOT NULL,
                tax_rate TEXT NOT NULL,
                mydata_mark TEXT,
                UNIQUE(invoice_number, buyer_tax_identifier)
            );
            CREATE TABLE IF NOT EXISTS debt_accounts (
                debt_account_id TEXT PRIMARY KEY,
                farmer_id TEXT NOT NULL REFERENCES farmers(farmer_id),
                debt_type TEXT NOT NULL,
                outstanding_eur TEXT NOT NULL,
                status TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS crisis_events (
                crisis_event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                name TEXT NOT NULL,
                claim_year INTEGER NOT NULL,
                event_start TEXT NOT NULL,
                affected_min_lat TEXT NOT NULL,
                affected_min_lon TEXT NOT NULL,
                affected_max_lat TEXT NOT NULL,
                affected_max_lon TEXT NOT NULL,
                policy_rule_version TEXT NOT NULL,
                event_end TEXT
            );
            CREATE TABLE IF NOT EXISTS audit_events (
                audit_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_id TEXT NOT NULL,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                metadata TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS document_records (
                document_id INTEGER PRIMARY KEY AUTOINCREMENT,
                farmer_id TEXT NOT NULL REFERENCES farmers(farmer_id),
                document_type TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                status TEXT NOT NULL,
                analysis TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self.connection.commit()

    def add_farmer(self, farmer: Farmer) -> Farmer:
        self._insert_dataclass("farmers", farmer)
        self.audit("system", "farmer.registered", "farmer", farmer.farmer_id, {"tax_identifier": farmer.tax_identifier})
        return farmer

    def add_parcel(self, parcel: Parcel) -> Parcel:
        self._insert_dataclass("parcels", parcel)
        self.audit("system", "parcel.registered", "parcel", parcel.parcel_id, {"farmer_id": parcel.farmer_id})
        return parcel

    def add_crop_season(self, crop_season: CropSeason) -> CropSeason:
        self._insert_dataclass("crop_seasons", crop_season)
        self.audit("system", "crop_season.enrolled", "crop_season", crop_season.crop_season_id, {})
        return crop_season

    def add_observation(self, observation: RemoteSensingObservation) -> RemoteSensingObservation:
        self._insert_dataclass("remote_sensing_observations", observation)
        self.audit("system", "remote_sensing.recorded", "observation", observation.observation_id, {})
        return observation

    def add_first_sale(self, first_sale: FirstSaleRecord) -> FirstSaleRecord:
        self._insert_dataclass("first_sale_records", first_sale)
        self.audit("system", "first_sale.recorded", "first_sale", first_sale.first_sale_id, {})
        return first_sale

    def add_debt(self, debt: DebtAccount) -> DebtAccount:
        self._insert_dataclass("debt_accounts", debt)
        self.audit("system", "debt.recorded", "debt", debt.debt_account_id, {})
        return debt

    def add_crisis_event(self, crisis_event: CrisisEvent) -> CrisisEvent:
        self._insert_dataclass("crisis_events", crisis_event)
        self.audit("system", "crisis.declared", "crisis_event", crisis_event.crisis_event_id, {})
        return crisis_event

    def get_farmer(self, farmer_id: str) -> Farmer:
        return self._get_dataclass("farmers", "farmer_id", farmer_id, Farmer)

    def get_parcel(self, parcel_id: str) -> Parcel:
        return self._get_dataclass("parcels", "parcel_id", parcel_id, Parcel)

    def get_crop_season(self, crop_season_id: str) -> CropSeason:
        return self._get_dataclass("crop_seasons", "crop_season_id", crop_season_id, CropSeason)

    def get_crisis_event(self, crisis_event_id: str) -> CrisisEvent:
        return self._get_dataclass("crisis_events", "crisis_event_id", crisis_event_id, CrisisEvent)

    def list_farmers(self) -> list[Farmer]:
        return self._list_dataclass("farmers", Farmer)

    def list_crisis_events(self) -> list[CrisisEvent]:
        return self._list_dataclass("crisis_events", CrisisEvent)

    def list_parcels(self, farmer_id: str | None = None) -> list[Parcel]:
        return self._list_dataclass("parcels", Parcel, "farmer_id", farmer_id)

    def list_crop_seasons(self, farmer_id: str | None = None, claim_year: int | None = None) -> list[CropSeason]:
        sql = "SELECT * FROM crop_seasons"
        params: list[Any] = []
        clauses = []
        if farmer_id is not None:
            clauses.append("farmer_id = ?")
            params.append(farmer_id)
        if claim_year is not None:
            clauses.append("claim_year = ?")
            params.append(claim_year)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        return [self._row_to_dataclass(row, CropSeason) for row in self.connection.execute(sql, params)]

    def list_observations(self, parcel_id: str, claim_year: int | None = None) -> list[RemoteSensingObservation]:
        sql = "SELECT * FROM remote_sensing_observations WHERE parcel_id = ?"
        params: list[Any] = [parcel_id]
        if claim_year is not None:
            sql += " AND claim_year = ?"
            params.append(claim_year)
        return [self._row_to_dataclass(row, RemoteSensingObservation) for row in self.connection.execute(sql, params)]

    def list_first_sales_for_crop(self, crop_season_id: str) -> list[FirstSaleRecord]:
        return self._list_dataclass("first_sale_records", FirstSaleRecord, "crop_season_id", crop_season_id)

    def list_debts(self, farmer_id: str) -> list[DebtAccount]:
        return self._list_dataclass("debt_accounts", DebtAccount, "farmer_id", farmer_id)

    def add_document_record(
        self, farmer_id: str, document_type: str, file_name: str, file_size: int, analysis: dict[str, Any]
    ) -> dict[str, Any]:
        cursor = self.connection.execute(
            """
            INSERT INTO document_records(farmer_id, document_type, file_name, file_size, status, analysis)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (farmer_id, document_type, file_name, file_size, "submitted", json.dumps(analysis, sort_keys=True)),
        )
        self.connection.commit()
        document_id = int(cursor.lastrowid)
        self.audit(
            "farmer-portal",
            "document.submitted",
            "document",
            str(document_id),
            {"farmer_id": farmer_id, "document_type": document_type, "file_name": file_name},
        )
        return self.get_document_record(document_id)

    def get_document_record(self, document_id: int) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM document_records WHERE document_id = ?", (document_id,)).fetchone()
        if row is None:
            raise KeyError(f"document record not found: {document_id}")
        return self._document_row(row)

    def list_document_records(self, farmer_id: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM document_records"
        params: list[Any] = []
        if farmer_id is not None:
            sql += " WHERE farmer_id = ?"
            params.append(farmer_id)
        sql += " ORDER BY document_id"
        return [self._document_row(row) for row in self.connection.execute(sql, params)]

    def audit(self, actor_id: str, action: str, entity_type: str, entity_id: str, metadata: dict[str, Any]) -> None:
        self.connection.execute(
            """
            INSERT INTO audit_events(actor_id, action, entity_type, entity_id, metadata)
            VALUES (?, ?, ?, ?, ?)
            """,
            (actor_id, action, entity_type, entity_id, json.dumps(metadata, sort_keys=True)),
        )
        self.connection.commit()

    def audit_events(self, entity_type: str | None = None, entity_id: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM audit_events"
        params: list[Any] = []
        clauses = []
        if entity_type is not None:
            clauses.append("entity_type = ?")
            params.append(entity_type)
        if entity_id is not None:
            clauses.append("entity_id = ?")
            params.append(entity_id)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY audit_event_id"
        return [dict(row) | {"metadata": json.loads(row["metadata"])} for row in self.connection.execute(sql, params)]

    def _document_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return dict(row) | {"analysis": json.loads(row["analysis"])}

    def _insert_dataclass(self, table_name: str, value: Any) -> None:
        row = self._dataclass_to_row(value)
        columns = list(row)
        placeholders = ", ".join("?" for _ in columns)
        sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"
        self.connection.execute(sql, [row[column] for column in columns])
        self.connection.commit()

    def _get_dataclass(self, table_name: str, id_column: str, entity_id: str, dataclass_type: type[T]) -> T:
        row = self.connection.execute(f"SELECT * FROM {table_name} WHERE {id_column} = ?", (entity_id,)).fetchone()
        if row is None:
            raise KeyError(f"{table_name} record not found: {entity_id}")
        return self._row_to_dataclass(row, dataclass_type)

    def _list_dataclass(
        self, table_name: str, dataclass_type: type[T], filter_column: str | None = None, filter_value: Any = None
    ) -> list[T]:
        sql = f"SELECT * FROM {table_name}"
        params: list[Any] = []
        if filter_column is not None and filter_value is not None:
            sql += f" WHERE {filter_column} = ?"
            params.append(filter_value)
        return [self._row_to_dataclass(row, dataclass_type) for row in self.connection.execute(sql, params)]

    def _dataclass_to_row(self, value: Any) -> dict[str, Any]:
        row: dict[str, Any] = {}
        for item in fields(value):
            field_value = getattr(value, item.name)
            if isinstance(field_value, Decimal):
                row[item.name] = str(field_value)
            elif isinstance(field_value, bool):
                row[item.name] = int(field_value)
            elif isinstance(field_value, dict):
                row[item.name] = json.dumps(field_value, sort_keys=True)
            elif field_value is None:
                row[item.name] = None
            else:
                row[item.name] = field_value
        return row

    def _row_to_dataclass(self, row: sqlite3.Row, dataclass_type: type[T]) -> T:
        values: dict[str, Any] = {}
        for item in fields(dataclass_type):
            field_value = row[item.name]
            if field_value is None:
                values[item.name] = None
            elif item.type in (Decimal, "Decimal") or "Decimal" in str(item.type):
                values[item.name] = Decimal(str(field_value))
            elif item.type in (bool, "bool"):
                values[item.name] = bool(field_value)
            elif "dict" in str(item.type):
                values[item.name] = json.loads(field_value)
            else:
                values[item.name] = field_value
        return dataclass_type(**values)
