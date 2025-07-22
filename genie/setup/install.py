from genie.setup.file import create_genie_folder
import frappe

def after_install():
    # Step 1: Call existing function
    create_genie_folder()

    # Step 2: Set default Genie Settings
    try:
        # Try to get existing settings
        doc = frappe.get_doc("Genie Settings")

        doc.update({
            "enable_ticket_raising": 1,
            "support_url": "https://helpdesk.botsolutions.tech",
            "api_token": "your_api_key:your_api_secret",  # ← replace this
            "save_recording": "Public",
            "max_recording_size": 0,
            "enable_portal_access": 0
        })

        doc.save(ignore_permissions=True)
        frappe.db.commit()
        frappe.logger().info("✅ Genie Settings updated with default values.")

    except frappe.DoesNotExistError:
        # If no settings doc exists, create one
        doc = frappe.new_doc("Genie Settings")
        doc.update({
            "enable_ticket_raising": 1,
            "support_url": "https://helpdesk.botsolutions.tech",
            "api_token": "176100fb0a8c612:81b45eefce99789",  # ← replace this
            "save_recording": "Public",
            "max_recording_size": 0,
            "enable_portal_access": 0
        })

        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        frappe.logger().info("✅ Genie Settings created and default values applied.")
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "❌ Error in Genie after_install")
