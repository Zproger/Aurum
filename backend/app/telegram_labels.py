"""Russian labels for names the database stores in English.

The web app translates the seeded default categories on display
(frontend/src/lib/categoryLabels.ts); the bot talks to the user in Russian, so
it needs the same mapping. Names the user typed are shown exactly as stored.
"""
from __future__ import annotations

from app.models.workspace import Workspace, WorkspaceKind
from app.services.workspace_service import PRIVATE_WORKSPACE_SUFFIX

# Keep in sync with backend/app/db/seed.py and the "category.*" keys in
# frontend/src/lib/i18n.ts.
DEFAULT_CATEGORY_LABELS = {
    "Housing & Utilities": "Жильё и коммуналка",
    "Groceries": "Продукты",
    "Dining Out": "Кафе и рестораны",
    "Transportation": "Транспорт",
    "Health & Fitness": "Здоровье и фитнес",
    "Shopping": "Покупки",
    "Entertainment": "Развлечения",
    "Subscriptions": "Подписки",
    "Salary": "Зарплата",
    "Freelance": "Фриланс",
    "Investments": "Инвестиции",
    "Gifts": "Подарки",
    "Business Income": "Доход от бизнеса",
    "Rental Income": "Сдача недвижимости",
    "Benefits": "Пособия и соцвыплаты",
    "Item Sales": "Продажа личных вещей",
    "Other Income": "Прочий доход",
    # The dashboard folds the smallest slices into this bucket.
    "Other": "Прочее",
}
PERSONAL_WORKSPACE_LABEL = "Личное пространство"


def category_label(name: str) -> str:
    return DEFAULT_CATEGORY_LABELS.get(name, name)


def workspace_label(workspace: Workspace) -> str:
    """The auto-generated «<name>'s private workspace» reads as «Личное
    пространство»; a personal space the user renamed keeps its own name."""
    if workspace.kind == WorkspaceKind.PERSONAL and workspace.display_name.endswith(PRIVATE_WORKSPACE_SUFFIX):
        return PERSONAL_WORKSPACE_LABEL
    return workspace.display_name
