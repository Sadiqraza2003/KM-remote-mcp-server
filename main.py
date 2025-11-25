# main.py
import asyncio
from fastmcp import FastMCP
from sqlalchemy.future import select
from sqlalchemy import update, delete, func
from db.database import engine, get_db, Base, AsyncSessionLocal
from models.Expense import Expense
from datetime import datetime
from sqlalchemy import delete, and_
from typing import Optional

mcp = FastMCP("ExpenseTracker")


#  Ensure tables exist (MySQL)
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ---------- TOOLS ---------- #

from datetime import datetime
# from fastmcp import tool
from models.Expense import Expense
from db.database import AsyncSessionLocal


@mcp.tool()
async def add_expense(
    user_id: str,
    date: str = None,
    amount: float = None,
    category: str = None,
    subcategory: str = "",
    note: str = ""
):
    """Add a new expense entry (user-specific). only amount date and category is mandatory."""
    print(">>> TOOL RECEIVED USER_ID:", user_id)
    if not date:
        return {
            "status": "ask_input",
            "field": "date",
            "message": "Please provide the date of the expense (YYYY-MM-DD)"
        }

    if amount is None:
        return {
            "status": "ask_input",
            "field": "amount",
            "message": "How much did you spend?"
        }

    if not category:
        return {
            "status": "ask_input",
            "field": "category",
            "message": "Please provide the expense category."
        }

    try:
        parsed_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        return {"status": "error", "message": "Invalid date format."}

    async with AsyncSessionLocal() as db:
        new_expense = Expense(
            user_id=user_id,   # IMPORTANT
            date=parsed_date,
            amount=amount,
            category=category,
            subcategory=subcategory or None,
            note=note or None
        )
        db.add(new_expense)
        await db.commit()
        await db.refresh(new_expense)

        return {
            "status": "ok",
            "message": f"Expense added!",
            "data": {
                "id": new_expense.id,
                "user_id": user_id,
                "date": str(parsed_date),
                "amount": amount,
                "category": category
            }
        }




@mcp.tool()
async def list_expenses(
    user_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    date: Optional[str] = None
):
    """
    List expenses:
    - for a specific date (date="YYYY-MM-DD")
    - OR for a date range (start_date + end_date)
    """

    # -------------------------------------------------
    # 1. LIST FOR SPECIFIC DATE
    # -------------------------------------------------
    if date:
        try:
            parsed_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            return {"status": "error", "message": "Invalid date format. Use YYYY-MM-DD."}

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Expense)
                .where(Expense.user_id == user_id)
                .where(Expense.date == parsed_date)
            )

            expenses = result.scalars().all()

            if not expenses:
                return {"status": "no_data", "message": f"No expenses found on {parsed_date}."}

            return {
                "status": "ok",
                "mode": "single_date",
                "date": str(parsed_date),
                "total": len(expenses),
                "expenses": [
                    {
                        "id": e.id,
                        "date": e.date.isoformat(),
                        "amount": e.amount,
                        "category": e.category,
                        "subcategory": e.subcategory,
                        "note": e.note
                    }
                    for e in expenses
                ]
            }

    # -------------------------------------------------
    # 2. LIST FOR DATE RANGE
    # -------------------------------------------------
    if start_date and end_date:
        # Validate dates
        try:
            parsed_start = datetime.strptime(start_date, "%Y-%m-%d").date()
            parsed_end = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            return {"status": "error", "message": "Invalid date format. Use YYYY-MM-DD."}

        if parsed_end < parsed_start:
            return {"status": "error", "message": "End date cannot be earlier than start date."}

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Expense)
                .where(Expense.user_id == user_id)
                .where(Expense.date.between(parsed_start, parsed_end))
                .order_by(Expense.date.asc())
            )

            expenses = result.scalars().all()

            if not expenses:
                return {
                    "status": "no_data",
                    "message": f"No expenses found between {parsed_start} and {parsed_end}."
                }

            return {
                "status": "ok",
                "mode": "range",
                "start_date": str(parsed_start),
                "end_date": str(parsed_end),
                "total": len(expenses),
                "expenses": [
                    {
                        "id": e.id,
                        "date": e.date.isoformat(),
                        "amount": e.amount,
                        "category": e.category,
                        "subcategory": e.subcategory,
                        "note": e.note
                    }
                    for e in expenses
                ]
            }

    # -------------------------------------------------
    # 3. Missing inputs → Ask the user
    # -------------------------------------------------
    if start_date and not end_date:
        return {
            "status": "ask_input",
            "field": "end_date",
            "message": f"You provided start_date ({start_date}). Please also provide end_date."
        }

    if end_date and not start_date:
        return {
            "status": "ask_input",
            "field": "start_date",
            "message": f"You provided end_date ({end_date}). Please also provide start_date."
        }

    return {
        "status": "ask_input",
        "field": "date_or_range",
        "message": "Please provide a date or a start_date + end_date to list expenses."
    }


@mcp.tool()
async def summarize(
    user_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    category: Optional[str] = None
):
    """
    Summarize total expenses (user-specific) within a date range.
    """

    #  Step 1: Check missing dates politely
    if not start_date and not end_date:
        return {
            "status": "ask_input",
            "field": "start_date",
            "message": "Please tell me the start date or date range to summarize your expenses (e.g., 2025-11-01)."
        }

    if start_date and not end_date:
        return {
            "status": "ask_input",
            "field": "end_date",
            "message": f"You provided a start date ({start_date}). Please provide the end date too."
        }

    if end_date and not start_date:
        return {
            "status": "ask_input",
            "field": "start_date",
            "message": f"You mentioned the end date ({end_date}). Please provide the start date."
        }

    #  Step 2: Validate date formats
    try:
        parsed_start = datetime.strptime(start_date, "%Y-%m-%d").date()
        parsed_end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        return {"status": "error", "message": "Invalid date format. Use YYYY-MM-DD."}

    #  Step 3: Validate date order
    if parsed_end < parsed_start:
        return {
            "status": "error",
            "message": f"End date ({parsed_end}) cannot be earlier than start date ({parsed_start})."
        }

    #  Step 4: Build user-specific query
    async with AsyncSessionLocal() as db:
        query = (
            select(Expense.category, func.sum(Expense.amount).label("total_amount"))
            .where(Expense.user_id == user_id)   # 🔥 Only this user's data
            .where(Expense.date.between(parsed_start, parsed_end))
        )

        if category:
            query = query.where(Expense.category.ilike(f"%{category}%"))

        query = query.group_by(Expense.category).order_by(Expense.category)

        result = await db.execute(query)
        data = result.all()

        #  Step 5: Handle no data
        if not data:
            if category:
                return {
                    "status": "no_data",
                    "message": f"No expenses found for category '{category}' between {parsed_start} and {parsed_end}."
                }
            return {
                "status": "no_data",
                "message": f"No expenses found between {parsed_start} and {parsed_end}."
            }

        #  Step 6: Compute summary
        total_sum = sum(float(row.total_amount) for row in data)
        breakdown = [
            {"category": row.category, "total_amount": float(row.total_amount)}
            for row in data
        ]

        #  Step 7: Build response
        msg = f"Here’s your expense summary from {parsed_start} to {parsed_end}."
        if category:
            msg += f" (Filtered by category: {category})"

        return {
            "status": "ok",
            "message": msg,
            "total_spent": round(total_sum, 2),
            "breakdown": breakdown,
        }


@mcp.tool()
async def edit_expense(
    user_id: str,
    id: Optional[int] = None,
    date: Optional[str] = None,
    amount: Optional[float] = None,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    note: Optional[str] = None,
    new_date: Optional[str] = None,
    new_amount: Optional[float] = None,
    new_category: Optional[str] = None,
    new_subcategory: Optional[str] = None,
    new_note: Optional[str] = None,
):
    """
    Edit an expense conversationally.
    User can identify expense by:
    - date
    - amount
    - category
    - or explicitly by id

    🔐 Fully user-isolated — user can only edit their own expenses.
    """

    async with AsyncSessionLocal() as db:

        # ----------------------------------------
        # STEP 1: If ID is not provided, find matches using filters
        # ----------------------------------------
        if id is None:
            filters = [Expense.user_id == user_id]  # 🔐 restrict to user's data

            if date:
                try:
                    parsed_date = datetime.strptime(date, "%Y-%m-%d").date()
                    filters.append(Expense.date == parsed_date)
                except ValueError:
                    return {"status": "error", "message": "Invalid date format. Use YYYY-MM-DD."}

            if amount is not None:
                filters.append(Expense.amount == amount)

            if category:
                filters.append(Expense.category.ilike(f"%{category}%"))

            # If no identifying filters provided
            if len(filters) == 1:  # only user_id filter
                return {
                    "status": "ask_input",
                    "field": "date",
                    "message": "Please provide a date, category, or amount to identify which expense you want to edit."
                }

            query = select(Expense).where(and_(*filters))
            result = await db.execute(query)
            matches = result.scalars().all()

            # No matches
            if not matches:
                return {
                    "status": "no_match",
                    "message": "No matching expenses found. Please provide a clearer date or amount."
                }

            # If multiple matches
            if len(matches) > 1:
                options = [
                    {
                        "id": e.id,
                        "date": str(e.date),
                        "amount": e.amount,
                        "category": e.category,
                        "subcategory": e.subcategory,
                        "note": e.note,
                    }
                    for e in matches
                ]
                return {
                    "status": "ask_choice",
                    "message": "Multiple matching expenses found. Please select which one you want to edit.",
                    "options": options,
                }

            # Exactly one match found
            id = matches[0].id

        # ----------------------------------------
        # STEP 2: Verify this ID actually belongs to this user
        # ----------------------------------------
        existing_expense = await db.execute(
            select(Expense).where(
                Expense.id == id,
                Expense.user_id == user_id  # 🔐 restrict by user
            )
        )
        expense = existing_expense.scalars().first()

        if not expense:
            return {
                "status": "error",
                "message": "❌ You cannot edit this expense because it does not belong to you."
            }

        # ----------------------------------------
        # STEP 3: Prepare update data
        # ----------------------------------------
        update_data = {}

        if new_date:
            try:
                update_data["date"] = datetime.strptime(new_date, "%Y-%m-%d").date()
            except ValueError:
                return {"status": "error", "message": "Invalid new date format. Use YYYY-MM-DD."}

        if new_amount is not None:
            update_data["amount"] = float(new_amount)

        if new_category:
            update_data["category"] = new_category

        if new_subcategory:
            update_data["subcategory"] = new_subcategory

        if new_note:
            update_data["note"] = new_note

        if not update_data:
            return {
                "status": "ask_input",
                "field": "fields",
                "message": "Please tell me which field(s) you want to update (amount, date, category, note, etc.)."
            }

        # ----------------------------------------
        # STEP 4: Apply update
        # ----------------------------------------
        await db.execute(
            update(Expense)
            .where(Expense.id == id, Expense.user_id == user_id)  # 🔐 prevent unauthorized edits
            .values(**update_data)
        )
        await db.commit()

        # ----------------------------------------
        # STEP 5: Return updated expense
        # ----------------------------------------
        updated = await db.get(Expense, id)

        return {
            "status": "ok",
            "message": f"Expense {id} updated successfully.",
            "updated_fields": list(update_data.keys()),
            "updated_expense": {
                "id": updated.id,
                "date": str(updated.date),
                "amount": updated.amount,
                "category": updated.category,
                "subcategory": updated.subcategory,
                "note": updated.note,
            }
        }



# @mcp.tool()
# async def delete_expense(id: int):
#     """Delete an expense entry by its ID."""
#     async with AsyncSessionLocal() as db:
#         result = await db.execute(delete(Expense).where(Expense.id == id))
#         await db.commit()

#         if result.rowcount == 0:
#             return {"status": "error", "message": f"No expense found with id={id}"}

#         return {"status": "ok", "message": f"Expense {id} deleted successfully"}

@mcp.tool()
async def delete_expense(
    user_id: str,
    category: Optional[str] = None,
    date: Optional[str] = None,
    id: Optional[int] = None
):
    """
    Delete an expense entry (user-specific):
    - by ID
    - or by category + date

    🔐 Only deletes expenses owned by the logged-in user.
    """

    async with AsyncSessionLocal() as db:

        # ----------------------------------------------------
        # 1. DELETE BY ID (only if expense belongs to this user)
        # ----------------------------------------------------
        if id is not None:
            result = await db.execute(
                delete(Expense).where(
                    Expense.id == id,
                    Expense.user_id == user_id   # 🔐 user isolation
                )
            )
            await db.commit()

            if result.rowcount == 0:
                return {
                    "status": "error",
                    "message": "❌ No expense found with this ID, or it does not belong to you."
                }

            return {
                "status": "ok",
                "message": f"Expense {id} deleted successfully."
            }

        # ----------------------------------------------------
        # 2. If no ID, require date
        # ----------------------------------------------------
        if not date:
            return {
                "status": "error",
                "message": "Please provide a date or an expense ID."
            }

        try:
            parsed_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            return {"status": "error", "message": "Invalid date format. Use YYYY-MM-DD."}

        # ----------------------------------------------------
        # 3. Find expense by category + date (user only)
        # ----------------------------------------------------
        filters = [
            Expense.user_id == user_id,   # 🔐 restrict to user
            Expense.date == parsed_date,
        ]

        if category:
            filters.append(Expense.category.ilike(f"%{category}%"))

        query = select(Expense).where(and_(*filters))
        result = await db.execute(query)
        expense = result.scalars().first()

        # ----------------------------------------------------
        # 4. Delete if exact match found
        # ----------------------------------------------------
        if expense:
            await db.execute(
                delete(Expense).where(
                    Expense.id == expense.id,
                    Expense.user_id == user_id  # 🔐 secure check
                )
            )
            await db.commit()

            return {
                "status": "ok",
                "message": f"Deleted expense on {parsed_date} in category '{expense.category}'."
            }

        # ----------------------------------------------------
        # 5. No match → show all expenses on that day for user
        # ----------------------------------------------------
        same_day = await db.execute(
            select(Expense)
            .where(
                Expense.user_id == user_id,  # 🔐 secure
                Expense.date == parsed_date
            )
        )
        same_day_expenses = same_day.scalars().all()

        if same_day_expenses:
            expense_list = [
                {
                    "id": e.id,
                    "category": e.category,
                    "subcategory": e.subcategory,
                    "amount": e.amount,
                    "note": e.note
                }
                for e in same_day_expenses
            ]

            return {
                "status": "ask_choice",
                "message": f"No exact match found for '{category}'. Here are your expenses on {parsed_date}:",
                "options": expense_list,
            }

        # ----------------------------------------------------
        # 6. No expenses at all that day
        # ----------------------------------------------------
        return {
            "status": "no_expense_on_day",
            "message": f"You have no expenses on {parsed_date}. Please provide a different date.",
        }



#MCP Resource
import os
CATEGORIES_PATH = os.path.join(os.path.dirname(__file__), "categories.json")

@mcp.resource("expense://categories", mime_type="application/json")
async def categories():
    print(">>> categories.json requested!")
    with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
        data = f.read()
        print(">>> categories.json content:", data[:80])  # preview
        return data



#MCP Prompt
from datetime import datetime
from fastmcp.prompts.prompt import PromptMessage, TextContent
current_date = datetime.now().strftime("%Y-%m-%d")

@mcp.prompt(
    name="kharchamind_system_prompt",
    title="KharchaMind Core System Prompt",
    description="Returns the full system prompt for KharchaMind with dynamic date injection.",
    tags={"system", "kharchamind", "expenses", "ai-assistant"},
)
def kharchamind_prompt() -> PromptMessage:
    prompt_text = f"""
You are **KharchaMind (💰)** — an intelligent AI Expense Management Assistant designed to help users in India track and manage their daily expenses.

It is currently **{current_date}**.  
Any relative dates like “today”, “yesterday”, “this week”, “last month” must be interpreted based on **{current_date}**.

---

#  Your Core Role:
Understand natural language messages and convert them into the correct action by calling the appropriate **MCP tools** for:
1. Adding a new expense
2. Editing an existing expense
3. Deleting an expense
4. Listing expenses for a date or date range
5. Summarizing total expenses
6. Handling follow-up questions when tool inputs are missing

---

#  CATEGORY RULES (VERY IMPORTANT)

You must **strictly** use the following categories and subcategories:
(Your categories list will go here)

DO NOT invent new categories or subcategories.
DO NOT rename categories.
DO NOT guess. Always match user input to your predefined categories.

---

# Behavior & Reasoning Guidelines

## 1. Natural Language Understanding
(… entire section …)

## 2. Missing Required Fields
(… entire section …)

## 3. Date Interpretation Rules
All dates are based on **{current_date}**.
(… entire section …)

## 4. MCP Tool Mappings
- Add → `add_expense(date, amount, category, subcategory, note)`
- Edit → `edit_expense(...)`
- Delete → `delete_expense`
- List → `list_expenses`
- Summary → `summarize`

## 5. Currency Rules
(… section …)

## 6. Tone & Personality
(… section …)

## 7. Error Handling
(… section …)

## 8. No Hallucinations
(… section …)

## 9. Out-of-scope Messages
(… section …)

---

# First-time Introduction:
“Hello!  I'm **KharchaMind (💰)** — your personal AI expense assistant…”

---
"""
    return PromptMessage(
        role="user",
        content=TextContent(type="text", text=prompt_text)
    )


# ---------- MCP ENTRY ---------- #

# if __name__ == "__main__":
#     asyncio.run(init_db())  # ensure tables exist before starting MCP server
#     mcp.run(transport="stdio")


if __name__ == "__main__":
    asyncio.run(init_db())  # ensure tables exist before starting MCP server
    mcp.run(transport="http", host="0.0.0.0", port=8000)





# Python main.py