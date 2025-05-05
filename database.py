import sqlite3
import logging
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

DB_PATH = "bot_data.db"

def setup_database():
    """Create database tables if they don't exist."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Create users table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            telegram_id INTEGER UNIQUE,
            search_count INTEGER DEFAULT 0,
            is_paid BOOLEAN DEFAULT 0,
            expiry_date TEXT
        )
        ''')

        # Create resources table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_code TEXT,
            subject_name TEXT,
            unit_number INTEGER,
            notes_link TEXT,
            ppt_link TEXT,
            pyq_link TEXT
        )
        ''')
        
        # Create pending payments table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS pending_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            reference_id TEXT UNIQUE,
            request_time TEXT,
            status TEXT DEFAULT 'pending'
        )
        ''')
        
        # Create subject access tracker table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS subject_access (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_code TEXT UNIQUE,
            access_count INTEGER DEFAULT 0
        )
        ''')
        
        conn.commit()
        logger.info("Database initialized successfully")
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
    finally:
        if conn:
            conn.close()

def get_user(telegram_id):
    """Get user information from the database."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        return cursor.fetchone()
    except sqlite3.Error as e:
        logger.error(f"Database error in get_user: {e}")
        return None
    finally:
        if conn:
            conn.close()

def create_user(telegram_id, username=None):
    """Create a new user in the database."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (telegram_id, search_count) VALUES (?, ?)",
            (telegram_id, 0)
        )
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error in create_user: {e}")
        return False
    finally:
        if conn:
            conn.close()

def increment_search_count(telegram_id):
    """Increment the search count for a user."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET search_count = search_count + 1 WHERE telegram_id = ?",
            (telegram_id,)
        )
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error in increment_search_count: {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_search_count(telegram_id):
    """Get the current search count for a user."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT search_count FROM users WHERE telegram_id = ?", (telegram_id,))
        result = cursor.fetchone()
        return result[0] if result else 0
    except sqlite3.Error as e:
        logger.error(f"Database error in get_search_count: {e}")
        return 0
    finally:
        if conn:
            conn.close()

def add_pending_payment(telegram_id, reference_id):
    """Add a pending payment to the database."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO pending_payments (telegram_id, reference_id, request_time) VALUES (?, ?, ?)",
            (telegram_id, reference_id, now)
        )
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error in add_pending_payment: {e}")
        return False
    finally:
        if conn:
            conn.close()

def verify_payment(reference_id, telegram_id=None):
    """Verify a payment by reference ID and activate subscription."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Find the pending payment
        if telegram_id:
            cursor.execute(
                "SELECT telegram_id FROM pending_payments WHERE reference_id = ? AND telegram_id = ?",
                (reference_id, telegram_id)
            )
        else:
            cursor.execute(
                "SELECT telegram_id FROM pending_payments WHERE reference_id = ? AND status = 'pending'",
                (reference_id,)
            )
            
        result = cursor.fetchone()
        
        if not result:
            return False
            
        payment_telegram_id = result[0]
        
        # Mark payment as verified
        cursor.execute(
            "UPDATE pending_payments SET status = 'verified' WHERE reference_id = ?",
            (reference_id,)
        )
        
        # Set payment status and expiry date (1 week from now)
        expiry_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "UPDATE users SET is_paid = 1, expiry_date = ? WHERE telegram_id = ?",
            (expiry_date, payment_telegram_id)
        )
        
        conn.commit()
        return payment_telegram_id
    except sqlite3.Error as e:
        logger.error(f"Database error in verify_payment: {e}")
        return False
    finally:
        if conn:
            conn.close()

def grant_access(telegram_id):
    """Grant subscription access to a user directly by telegram_id."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,))
        result = cursor.fetchone()
        
        if not result:
            # User doesn't exist, create them first
            create_user(telegram_id)
        
        # Set payment status and expiry date (1 week from now)
        expiry_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "UPDATE users SET is_paid = 1, expiry_date = ? WHERE telegram_id = ?",
            (expiry_date, telegram_id)
        )
        
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error in grant_access: {e}")
        return False
    finally:
        if conn:
            conn.close()

def check_subscription(telegram_id):
    """Check if a user has an active subscription."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT is_paid, expiry_date FROM users WHERE telegram_id = ?",
            (telegram_id,)
        )
        result = cursor.fetchone()
        
        if not result:
            return False
            
        is_paid, expiry_date = result
        
        if not is_paid:
            return False
            
        if not expiry_date:
            return False
            
        # Check if subscription has expired
        now = datetime.now()
        expiry = datetime.strptime(expiry_date, "%Y-%m-%d %H:%M:%S")
        
        if now > expiry:
            # Reset payment status if expired
            cursor.execute(
                "UPDATE users SET is_paid = 0, expiry_date = NULL WHERE telegram_id = ?",
                (telegram_id,)
            )
            conn.commit()
            return False
            
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error in check_subscription: {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_subscription_expiry(telegram_id):
    """Get the expiry date of a user's subscription."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check user table first for expiry date
        cursor.execute(
            "SELECT is_paid, expiry_date FROM users WHERE telegram_id = ?",
            (telegram_id,)
        )
        result = cursor.fetchone()
        
        if not result:
            return None
            
        is_paid, expiry_date = result
        
        if not is_paid or not expiry_date:
            return None
            
        # Parse expiry date
        expiry = datetime.strptime(expiry_date, "%Y-%m-%d %H:%M:%S")
        
        # Check if already expired
        now = datetime.now()
        if now > expiry:
            return None
            
        return expiry
    except sqlite3.Error as e:
        logger.error(f"Database error in get_subscription_expiry: {e}")
        return None
    finally:
        if conn:
            conn.close()

def add_resource(subject_code, subject_name, unit_number, notes_link=None, ppt_link=None, pyq_link=None):
    """Add or update a resource in the database."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if the entry exists
        cursor.execute(
            "SELECT id FROM resources WHERE subject_code = ? AND unit_number = ?",
            (subject_code.upper(), unit_number)
        )
        
        existing_id = cursor.fetchone()
        
        if existing_id:
            # Update existing entry
            update_query = "UPDATE resources SET subject_name = ?"
            params = [subject_name]
            
            if notes_link:
                update_query += ", notes_link = ?"
                params.append(notes_link)
                
            if ppt_link:
                update_query += ", ppt_link = ?"
                params.append(ppt_link)
                
            if pyq_link:
                update_query += ", pyq_link = ?"
                params.append(pyq_link)
                
            update_query += " WHERE id = ?"
            params.append(existing_id[0])
            
            cursor.execute(update_query, params)
        else:
            # Insert new entry
            cursor.execute(
                """INSERT INTO resources (subject_code, subject_name, unit_number, notes_link, ppt_link, pyq_link) 
                VALUES (?, ?, ?, ?, ?, ?)""",
                (subject_code.upper(), subject_name, unit_number, notes_link, ppt_link, pyq_link)
            )
            
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error in add_resource: {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_resources(subject_code):
    """Get all resources for a subject code with placeholders for all 6 units."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # First, get subject name
        cursor.execute(
            "SELECT DISTINCT subject_name FROM resources WHERE subject_code = ? LIMIT 1",
            (subject_code.upper(),)
        )
        subject_row = cursor.fetchone()
        
        if not subject_row:
            return None, None
            
        subject_name = subject_row['subject_name']
        
        # Then get all resources
        cursor.execute(
            """
            SELECT unit_number, notes_link, ppt_link, pyq_link 
            FROM resources 
            WHERE subject_code = ? 
            ORDER BY unit_number
            """,
            (subject_code.upper(),)
        )
        
        # Initialize with empty placeholders for all 6 units
        resources = {}
        for unit in range(1, 7):  # Units 1-6
            resources[unit] = {}
        
        # Fill in available resources
        for row in cursor.fetchall():
            unit = row['unit_number']
            notes_link = row['notes_link']
            ppt_link = row['ppt_link']
            pyq_link = row['pyq_link']
            
            if notes_link:
                resources[unit]['notes'] = notes_link
            if ppt_link:
                resources[unit]['ppt'] = ppt_link
            if pyq_link:
                resources[unit]['pyq'] = pyq_link
            
        return subject_name, resources
    except sqlite3.Error as e:
        logger.error(f"Database error in get_resources: {e}")
        return None, None
    finally:
        if conn:
            conn.close()

def remove_resource(subject_code, unit_number, resource_type):
    """Remove a specific resource (notes, ppt, or pyq) for a subject and unit."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if the entry exists
        cursor.execute(
            "SELECT id, notes_link, ppt_link, pyq_link FROM resources WHERE subject_code = ? AND unit_number = ?",
            (subject_code.upper(), unit_number)
        )
        
        existing = cursor.fetchone()
        
        if not existing:
            return False, "Resource not found"
        
        resource_id, notes_link, ppt_link, pyq_link = existing
        
        # Prepare update query based on resource type
        if resource_type == 'notes':
            if not notes_link:
                return False, "Notes resource not found"
            update_query = "UPDATE resources SET notes_link = NULL WHERE id = ?"
        elif resource_type == 'ppt':
            if not ppt_link:
                return False, "PPT resource not found"
            update_query = "UPDATE resources SET ppt_link = NULL WHERE id = ?"
        elif resource_type == 'pyq':
            if not pyq_link:
                return False, "PYQ resource not found"
            update_query = "UPDATE resources SET pyq_link = NULL WHERE id = ?"
        else:
            return False, "Invalid resource type"
        
        cursor.execute(update_query, (resource_id,))
        
        # If all resources are NULL after update, delete the row
        cursor.execute(
            "SELECT notes_link, ppt_link, pyq_link FROM resources WHERE id = ?",
            (resource_id,)
        )
        updated = cursor.fetchone()
        
        if updated and updated[0] is None and updated[1] is None and updated[2] is None:
            cursor.execute("DELETE FROM resources WHERE id = ?", (resource_id,))
        
        conn.commit()
        return True, "Resource removed successfully"
    except sqlite3.Error as e:
        logger.error(f"Database error in remove_resource: {e}")
        return False, f"Database error: {e}"
    finally:
        if conn:
            conn.close()

def edit_resource(subject_code, unit_number, resource_type, new_link):
    """Edit a specific resource link for a subject and unit."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if the entry exists
        cursor.execute(
            "SELECT id, subject_name FROM resources WHERE subject_code = ? AND unit_number = ?",
            (subject_code.upper(), unit_number)
        )
        
        existing = cursor.fetchone()
        
        if not existing:
            return False, "Resource not found"
        
        resource_id, subject_name = existing
        
        # Prepare update query based on resource type
        if resource_type == 'notes':
            update_query = "UPDATE resources SET notes_link = ? WHERE id = ?"
        elif resource_type == 'ppt':
            update_query = "UPDATE resources SET ppt_link = ? WHERE id = ?"
        elif resource_type == 'pyq':
            update_query = "UPDATE resources SET pyq_link = ? WHERE id = ?"
        else:
            return False, "Invalid resource type"
        
        cursor.execute(update_query, (new_link, resource_id))
        conn.commit()
        
        return True, f"Resource updated successfully for {subject_code} Unit {unit_number}"
    except sqlite3.Error as e:
        logger.error(f"Database error in edit_resource: {e}")
        return False, f"Database error: {e}"
    finally:
        if conn:
            conn.close()

def delete_subject(subject_code):
    """Delete all resources for a given subject code."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if the subject exists
        cursor.execute(
            "SELECT COUNT(*) FROM resources WHERE subject_code = ?",
            (subject_code.upper(),)
        )
        
        count = cursor.fetchone()[0]
        
        if count == 0:
            return False, "Subject not found"
        
        # Delete all resources for the subject
        cursor.execute("DELETE FROM resources WHERE subject_code = ?", (subject_code.upper(),))
        conn.commit()
        
        return True, f"Deleted all resources for {subject_code} ({count} entries removed)"
    except sqlite3.Error as e:
        logger.error(f"Database error in delete_subject: {e}")
        return False, f"Database error: {e}"
    finally:
        if conn:
            conn.close()

def increment_subject_access(subject_code):
    """Increment the access count for a subject code."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if the subject code exists in the tracker
        cursor.execute(
            "SELECT access_count FROM subject_access WHERE subject_code = ?",
            (subject_code.upper(),)
        )
        result = cursor.fetchone()
        
        if result:
            # Increment existing subject
            cursor.execute(
                "UPDATE subject_access SET access_count = access_count + 1 WHERE subject_code = ?",
                (subject_code.upper(),)
            )
        else:
            # Add new subject entry
            cursor.execute(
                "INSERT INTO subject_access (subject_code, access_count) VALUES (?, 1)",
                (subject_code.upper(),)
            )
        
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error in increment_subject_access: {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_most_accessed_subject():
    """Get the most frequently accessed subject code."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT subject_code, access_count FROM subject_access ORDER BY access_count DESC LIMIT 1"
        )
        result = cursor.fetchone()
        
        if result:
            return result[0]  # Return just the subject code
        else:
            return None
    except sqlite3.Error as e:
        logger.error(f"Database error in get_most_accessed_subject: {e}")
        return None
    finally:
        if conn:
            conn.close()

def get_pending_verification_requests():
    """Get all pending payment verification requests with user information."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Get all pending payments with user telegram_id and reference_id
        cursor.execute("""
            SELECT p.telegram_id, p.reference_id, p.request_time 
            FROM pending_payments p 
            WHERE p.status = 'pending' 
            ORDER BY p.request_time DESC
        """)
        
        pending_requests = []
        for row in cursor.fetchall():
            pending_requests.append({
                "telegram_id": row[0],
                "reference_id": row[1],
                "request_time": row[2]
            })
        
        return pending_requests
    except sqlite3.Error as e:
        logger.error(f"Database error in get_pending_verification_requests: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_user_stats():
    """Get statistics about users and payments."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Total users
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        # Active subscribers
        cursor.execute(
            "SELECT COUNT(*) FROM users WHERE is_paid = 1 AND datetime(expiry_date) > datetime('now')"
        )
        active_subscribers = cursor.fetchone()[0]
        
        # Total verified payments
        cursor.execute("SELECT COUNT(*) FROM pending_payments WHERE status = 'verified'")
        total_payments = cursor.fetchone()[0]
        
        # Pending payments
        cursor.execute("SELECT COUNT(*) FROM pending_payments WHERE status = 'pending'")
        pending_payments = cursor.fetchone()[0]
        
        # Total resources
        cursor.execute("SELECT COUNT(*) FROM resources")
        total_resources = cursor.fetchone()[0]
        
        # Subject count
        cursor.execute("SELECT COUNT(DISTINCT subject_code) FROM resources")
        subject_count = cursor.fetchone()[0]
        
        # Most accessed subject
        most_accessed_subject = get_most_accessed_subject()
        
        return {
            "total_users": total_users,
            "active_subscribers": active_subscribers,
            "total_payments": total_payments,
            "pending_payments": pending_payments,
            "total_resources": total_resources,
            "subject_count": subject_count,
            "most_accessed_subject": most_accessed_subject
        }
    except sqlite3.Error as e:
        logger.error(f"Database error in get_user_stats: {e}")
        return None
    finally:
        if conn:
            conn.close()
