"""Kiểm tra PostgreSQL schema v4 sau khi nâng cấp Alembic."""

from sqlalchemy import inspect, text

from database import engine


def main() -> None:
    """Kiểm tra bảng phát hành, metadata file và revision Alembic."""
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Chỉ kiểm tra schema v4 trên PostgreSQL.")

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert "model_releases" in tables
    columns = {c["name"] for c in inspector.get_columns("model_versions")}
    assert {"version", "file_path", "created_at", "sha256", "size_bytes"}.issubset(columns)
    release_pk = set(inspector.get_pk_constraint("model_releases")["constrained_columns"])
    assert release_pk == {"release_id"}
    fks = inspector.get_foreign_keys("model_releases")
    assert any(
        f["constrained_columns"] == ["version"]
        and f["referred_table"] == "model_versions"
        for f in fks
    )
    with engine.connect() as db:
        revision = db.scalar(text("SELECT version_num FROM alembic_version"))
        assert revision == "0004_model_management", revision
    print("POSTGRESQL SCHEMA V4: PASS")


if __name__ == "__main__":
    main()
