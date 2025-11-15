import pandas as pd
from sqlalchemy import MetaData
from pathlib import Path


class CSVProductValidator:

    def __init__(self, engine=None, table_name="products"):
        self.engine = engine
        self.table_name = table_name

        self.forbidden = {"status"}
        self.db_columns = None
        self.expected_csv_columns = None
        self.product_table = None

        # NEW: store SKUs seen so far to avoid duplicates across file
        self._seen_skus = set()

        if engine is not None:
            self._load_db_schema()


    # -------------------------------
    # LOAD DB SCHEMA
    # -------------------------------
    def _load_db_schema(self):
        metadata = MetaData()
        metadata.reflect(bind=self.engine)

        if self.table_name not in metadata.tables:
            raise ValueError(f"Table '{self.table_name}' does not exist in DB.")

        self.product_table = metadata.tables[self.table_name]
        self.db_columns = [c.name for c in self.product_table.columns]

        self.expected_csv_columns = [
            c for c in self.db_columns if c not in self.forbidden
        ]


    # -------------------------------
    # REMOVE DUPLICATES INSIDE CSV FILE
    # -------------------------------
    def remove_in_file_duplicates(self, chunk: pd.DataFrame):
        """
        Removes:
        - duplicates IN THE SAME CHUNK
        - duplicates already seen in previous chunks (same CSV file)

        Keeps only the first occurrence of each SKU.
        """

        if "sku" not in chunk.columns:
            return chunk  # fail-safe

        # Remove internal duplicates inside the chunk
        chunk = chunk.drop_duplicates(subset=["sku"], keep="first")

        # Remove rows whose SKU already appeared in earlier chunks
        new_chunk = chunk[~chunk["sku"].isin(self._seen_skus)]

        # Add remaining SKUs to the global seen list
        self._seen_skus.update(new_chunk["sku"].tolist())

        return new_chunk


    # -------------------------------
    # SAVE UPLOADED CSV FILE
    # -------------------------------
    async def save_uploaded_csv(self, file, folder="temp_csv"):
        Path(folder).mkdir(parents=True, exist_ok=True)
        file_path = Path(folder) / file.filename

        with open(file_path, "wb") as f:
            f.write(await file.read())

        return str(file_path)


    # -------------------------------
    # VALIDATE CSV HEADER
    # -------------------------------
    def validate_and_fix_header(self, csv_path: str):

        if self.expected_csv_columns is None:
            raise RuntimeError("Engine not set. Call _load_db_schema().")

        csv_path = Path(csv_path)
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        df = pd.read_csv(csv_path, nrows=0)
        csv_columns = list(df.columns)

        forbidden_found = set(csv_columns) & self.forbidden
        if forbidden_found:
            raise ValueError(f"CSV contains forbidden columns: {forbidden_found}")

        missing = set(self.expected_csv_columns) - set(csv_columns)
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        extra = set(csv_columns) - set(self.expected_csv_columns)
        if extra:
            raise ValueError(f"CSV contains extra invalid columns: {extra}")

        if csv_columns != self.expected_csv_columns:
            return False, "reorder_required"

        return True, "header_valid"


    # -------------------------------
    # LOAD CSV STREAMING IN CHUNKS
    # -------------------------------
    def load_csv_chunks_ordered(self, csv_path: str, chunksize=50000):

        if self.expected_csv_columns is None:
            raise RuntimeError("Engine not set. Call _load_db_schema().")

        # reset seen SKUs for a new file upload
        self._seen_skus = set()

        for chunk in pd.read_csv(csv_path, chunksize=chunksize):
            chunk = chunk[self.expected_csv_columns]

            # NEW: remove duplicates inside file
            chunk = self.remove_in_file_duplicates(chunk)

            if not chunk.empty:
                yield chunk
