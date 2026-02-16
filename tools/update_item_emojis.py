import asyncio
import aiosqlite

DB_PATH = "myuu.db"  # adjust if your DB is elsewhere

async def main():
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        # get all items
        cur = await conn.execute("SELECT id, name, emoji FROM items ORDER BY id;")
        items = await cur.fetchall()
        await cur.close()

        print("Current items loaded:", len(items))
        print("For each item, paste the FULL emoji code (<:name:id>) or leave blank to skip.\n")

        for row in items:
            item_id = row["id"]
            name = row["name"]
            old_emoji = row["emoji"]

            print(f"\nItem: {name} (id={item_id})")
            if old_emoji:
                print(f"Existing emoji: {old_emoji}")

            new_emoji = input("Paste emoji code (<:name:id>) or press Enter to skip: ").strip()
            if new_emoji:
                await conn.execute(
                    "UPDATE items SET emoji = ? WHERE id = ?",
                    (new_emoji, item_id)
                )
                print(f"✅ Updated {name} → {new_emoji}")
            else:
                print("⏩ Skipped")

        await conn.commit()
        print("\n🎉 All done! Changes saved.")

if __name__ == "__main__":
    asyncio.run(main())
