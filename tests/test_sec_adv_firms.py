import csv
import io
import zipfile

import pyarrow.parquet as pq

from er.datasources.common.parquet_writer import BatchedParquetWriter
from er.datasources.sec_adv_firms.ingest import parse_zip
from er.datasources.sec_adv_firms.schema import CLIENT_TYPE_SCHEMA, FIRM_SCHEMA


def test_monthly_file_parses_padded_amounts_and_dates_the_snapshot_by_its_newest_filing(tmp_path):
    header = ["Organization CRD#", "Primary Business Name", "Latest ADV Filing Date", "1P", "CIK#", "5F(2)(c)", "5A",
              "5D(f)(1)", "5D(f)(3)", "5D(l)(2)", "5D(l)(3)"]
    rows = [
        ["111883", "AQR CAPITAL MANAGEMENT, LLC", "08/27/2026", "549300GC5MDF1KXYMP06", "1167557",
         "       311,703,264,770.00", "728", "240", "  154,600,000,000.00", "", ""],
        ["38", "SMALL ADVISER", "10/01/2026", "NOT-AN-LEI", "", "                      .00", " 12", "", "",
         "Fewer than 5 clients", "  13,300,000.00"],
    ]
    buffer = io.StringIO()
    csv.writer(buffer).writerows([header, *rows])
    path = tmp_path / "ia100226.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ia09012026.csv", buffer.getvalue().encode("latin-1"))
    firms = BatchedParquetWriter(tmp_path / "firms.parquet", FIRM_SCHEMA)
    clients = BatchedParquetWriter(tmp_path / "clients.parquet", CLIENT_TYPE_SCHEMA)

    assert parse_zip(path, firms, clients, set()) == 2
    firms.close()
    clients.close()

    by_crd = {row["crd_number"]: row for row in pq.read_table(tmp_path / "firms.parquet").to_pylist()}
    aqr, small = by_crd["111883"], by_crd["38"]
    assert (aqr["raum"], aqr["employees"], aqr["cik"], aqr["lei"]) == (311703264770.0, 728, "0001167557", "549300GC5MDF1KXYMP06")
    assert aqr["snapshot_date"] == small["snapshot_date"] == "2026-10-01"
    assert (small["raum"], small["lei"]) == (0.0, None)
    by_type = {(row["crd_number"], row["client_type"]): row for row in pq.read_table(tmp_path / "clients.parquet").to_pylist()}
    assert by_type[("111883", "Pooled investment vehicles")]["client_count"] == 240
    fewer = by_type[("38", "Sovereign wealth funds and foreign official institutions")]
    assert fewer["fewer_than_five"] and fewer["client_count"] is None and fewer["raum"] == 13300000.0
