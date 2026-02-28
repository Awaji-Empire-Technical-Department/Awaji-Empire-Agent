import os
import sys

# Try to find python-dotenv and mysql-connector
try:
    import mysql.connector
    from dotenv import load_dotenv
except ImportError:
    print("Error: Required packages not found.")
    print("Please run this script inside your Python virtual environment where discord_bot is running.")
    print("Example: cd discord_bot && uv run python ../db_repair.py")
    sys.exit(1)

def main():
    # Try to load envs from discord_bot/.env
    env_path = os.path.join(os.path.dirname(__file__), 'discord_bot', '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
    else:
        load_dotenv() # try default

    db_host = os.getenv('DB_HOST', 'localhost')
    db_name = os.getenv('DB_NAME')
    db_user = os.getenv('DB_USER')
    db_password = os.getenv('DB_PASS')

    if not db_name:
        print("Error: Could not find DB credentials in environment.")
        sys.exit(1)

    try:
        conn = mysql.connector.connect(
            host=db_host,
            database=db_name,
            user=db_user,
            password=db_password
        )
        cursor = conn.cursor()

        print(f"Connected to database: {db_name}")

        # 1. Delete failed migration records
        print("Cleaning up _sqlx_migrations table...")
        cursor.execute("DELETE FROM _sqlx_migrations WHERE version IN (6, 100);")
        conn.commit()
        print("Rows for migration 6 and 100 removed.")

        # 2. Drop the columns so migration 100 can run cleanly
        columns_to_drop = [
            ("lobby_members", "status"),
            ("tournament_matches", "round_num"),
            ("tournament_matches", "match_index"),
            ("tournament_matches", "next_match_id"),
            ("tournament_matches", "score1"),
            ("tournament_matches", "score2"),
            ("tournament_matches", "win_condition"),
        ]

        print("Dropping existing columns to allow clean migration...")
        for table, column in columns_to_drop:
            try:
                query = f"ALTER TABLE {table} DROP COLUMN {column};"
                cursor.execute(query)
                print(f"  ✓ Dropped {column} from {table}")
            except mysql.connector.Error as err:
                # 1091 is "Can't drop column; check that column/key exists"
                if err.errno == 1091:
                    print(f"  - Column {column} in {table} already dropped.")
                else:
                    print(f"  ! Error dropping {column}: {err}")

        conn.commit()
        cursor.close()
        conn.close()

        print("\n=== REPAIR SUCCESSFUL ===")
        print("You can now safely restart the `database_bridge` application.")
        print("The database migration 100 will run from scratch and apply cleanly.")

    except mysql.connector.Error as err:
        print(f"Database error: {err}")
        sys.exit(1)

if __name__ == "__main__":
    main()
