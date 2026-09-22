from datetime import date as date_
from decimal import Decimal

from pydantic import BaseModel, Field


class CategoryRankingChildItem(BaseModel):
    """One subcategory's (or the parent's own direct, un-subcategorized)
    share of a CategoryRankingItem's total — see
    services/category_rollup.py's CategoryRollupChildItem."""

    category_id: int
    name: str
    color: str
    icon: str | None
    amount: Decimal


class CategorySpendingPoint(BaseModel):
    year: int
    month: int
    amount: Decimal


class CategorySpendingReport(BaseModel):
    category_id: int
    category_name: str
    category_color: str
    category_icon: str | None
    start_date: date_ | None
    end_date: date_ | None
    total_amount: Decimal
    transaction_count: int
    average_per_month: Decimal
    series: list[CategorySpendingPoint]


class CategoryRankingItem(BaseModel):
    category_id: int
    name: str
    color: str
    icon: str | None
    amount: Decimal
    percent: float
    transaction_count: int
    # Populated only when this category's spend came from more than one
    # distinct category (subcategories, or a mix of itself and its
    # children) — e.g. a receipt split across "Groceries" subcategories.
    children: list[CategoryRankingChildItem] = Field(default_factory=list)


class CategoryRankingReport(BaseModel):
    start_date: date_ | None
    end_date: date_ | None
    total_amount: Decimal
    items: list[CategoryRankingItem]


class TagRankingCategoryItem(BaseModel):
    """One top-level category's share of a tag's total — see
    services/tag_rollup.py's TagRollupCategoryItem. category_id is null (and
    name empty) for the share that had no category at all."""

    category_id: int | None
    name: str
    color: str
    icon: str | None
    amount: Decimal


class TagRankingItem(BaseModel):
    tag_id: int
    name: str
    color: str
    amount: Decimal
    # Share of the period's *total* spending of this kind, not of the tagged
    # part of it — tags overlap, so these percentages are each meaningful on
    # their own but deliberately don't add up to 100.
    percent: float
    transaction_count: int
    categories: list[TagRankingCategoryItem] = Field(default_factory=list)


class TagRankingReport(BaseModel):
    start_date: date_ | None
    end_date: date_ | None
    # Everything spent/earned in the period, tagged or not — the denominator
    # behind each item's percent.
    total_amount: Decimal
    # The part of total_amount carrying at least one tag, counted once per
    # transaction however many tags it has. total_amount - tagged_amount is
    # what's still untagged, so the two together say how much of the period
    # this report actually covers.
    tagged_amount: Decimal
    items: list[TagRankingItem]


class TagSpendingReport(BaseModel):
    """One tag's month-by-month total — the tag-side twin of
    CategorySpendingReport, reusing its CategorySpendingPoint since a point
    is just (year, month, amount) either way."""

    tag_id: int
    tag_name: str
    start_date: date_ | None
    end_date: date_ | None
    total_amount: Decimal
    transaction_count: int
    average_per_month: Decimal
    series: list[CategorySpendingPoint]
