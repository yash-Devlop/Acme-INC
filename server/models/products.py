from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import Text, SmallInteger, Index
from sqlalchemy.dialects.postgresql import CITEXT

ProductBase = declarative_base()

class Product(ProductBase):
    __tablename__ = "products"

    sku: Mapped[str] = mapped_column(
        CITEXT,
        primary_key=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        server_default="1"
    )  # 1 = active, 0 = inactive

    __table_args__ = (
        Index("idx_status", "status"),
    )