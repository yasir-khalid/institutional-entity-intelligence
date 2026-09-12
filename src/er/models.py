from __future__ import annotations

from pydantic import BaseModel


class GleifEntity(BaseModel):
    lei: str
    legal_name: str
    legal_name_norm: str = ""
    legal_name_core: str = ""
    aliases: list[str] = []
    aliases_norm: list[str] = []

    entity_status: str | None = None
    entity_category: str | None = None
    jurisdiction: str | None = None
    legal_form_code: str | None = None

    registration_authority_id: str | None = None
    registration_id: str | None = None
    registration_status: str | None = None

    legal_address_line1: str | None = None
    legal_city: str | None = None
    legal_region: str | None = None
    legal_postcode: str | None = None
    legal_country: str | None = None

    hq_address_line1: str | None = None
    hq_city: str | None = None
    hq_region: str | None = None
    hq_postcode: str | None = None
    hq_country: str | None = None

    initial_registration_date: str | None = None
    last_update_date: str | None = None
    next_renewal_date: str | None = None

    # derived fields
    name_tokens: list[str] = []
    postcode_prefix: str | None = None
    fund_number: int | None = None
    is_master: bool = False
    is_feeder: bool = False
    is_offshore: bool = False
    is_domestic: bool = False


class GleifRelationship(BaseModel):
    start_node_id: str
    start_node_id_type: str | None = None
    end_node_id: str
    end_node_id_type: str | None = None
    relationship_type: str | None = None
    relationship_status: str | None = None
    start_date: str | None = None
    end_date: str | None = None


class GleifException(BaseModel):
    lei: str
    exception_category: str | None = None
    exception_reason: str | None = None
