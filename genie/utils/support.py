# Copyright (c) 2023, Wahni IT Solutions Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import cint, flt, get_url, now
from frappe.utils.safe_exec import get_safe_globals, safe_eval
from genie.utils.requests import make_request
import requests
import json
import urllib.parse


@frappe.whitelist()
def create_ticket(title, description, custom_site_name, raised_by, screen_recording=None):
    settings = frappe.get_cached_doc("Genie Settings")
    headers = {
        "Authorization": f"token {settings.get_password('support_api_token')}",
    }

    hd_ticket_file = None
    if screen_recording:
        screen_recording = f"{get_url()}{screen_recording}"
        hd_ticket_file = make_request(
            method="POST",  # Added method parameter
            url=f"{settings.support_url}/api/method/upload_file",
            headers=headers,
            payload={"file_url": screen_recording}
        ).get("message")

    hd_ticket = make_request(
        method="POST",  # Added method parameter
        url=f"{settings.support_url}/api/method/helpdesk.helpdesk.doctype.hd_ticket.api.new",
        headers=headers,
        payload={
            "doc": {
                "description": description,
                "subject": title,
                "custom_site_name": custom_site_name,
                "raised_by": raised_by,
                **generate_ticket_details(settings),
            },
            "attachments": [hd_ticket_file] if hd_ticket_file else [],
        }
    ).get("message", {}).get("name")

    return hd_ticket


def generate_ticket_details(settings):
	req_params = {}
	for row in settings.ticket_details:
		if row.type == "String":
			req_params[row.key] = row.value
		elif row.type == "Integer":
			req_params[row.key] = cint(row.value)
		elif row.type == "Context":
			req_params[row.key] = safe_eval(row.value, get_safe_globals(), {})
		else:
			req_params[row.key] = row.value

		if row.cast_to:
			if row.cast_to == "Int":
				req_params[row.key] = cint(req_params[row.key])
			elif row.cast_to == "String":
				req_params[row.key] = str(req_params[row.key])
			elif row.cast_to == "Float":
				req_params[row.key] = flt(req_params[row.key])

	return req_params


def upload_file(content):
	file_url = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": frappe.scrub(f"ST_{frappe.session.user}_{now()}.mp4"),
			"is_private": False,
			"content": content,
			"decode": True,
		}
	).save(ignore_permissions=True).file_url

	return f"{get_url()}{file_url}"


@frappe.whitelist()
def get_portal_url():
	settings = frappe.get_cached_doc("Genie Settings")
	response = make_request(
		url=f"{settings.support_url}/api/method/login",
		headers={
			"Content-Type": "application/json",
		},
		payload={
			"usr": settings.get_password("portal_user"),
			"pwd": settings.get_password("portal_user_password"),
		},
		return_response=True
	)

	sid = response.cookies.get("sid")
	return {
		"url": f"{settings.support_url}/helpdesk?sid={sid}"
	}

import re
import json
import frappe
import requests
from urllib.parse import quote  # Add this import for quote function

@frappe.whitelist()
def sync_domain_tickets():
    # Get the current site URL dynamically and add 'https://' to the URL
    current_site_url = "https://" + frappe.local.site  # Adding the 'https://' prefix to the current site URL
    print(f"Current Site URL: {current_site_url}")  # Debug: Check if the site URL is being fetched correctly

    settings = frappe.get_cached_doc("Genie Settings")

    headers = {
        "Authorization": f"token {settings.get_password('support_api_token')}",
        "Content-Type": "application/json",
    }

    # Dynamically set the filter based on the current site
    filters = json.dumps([["custom_site_name", "=", current_site_url]])  # Dynamically fetch the filter
    fields = json.dumps(["*"])

    url = f"{settings.support_url}/api/v2/document/HD Ticket?fields={quote(fields)}&filters={quote(filters)}"

    print("🚀 Sync started")
    print(f"🌐 API URL: {url}")  # Debug: Check if the URL is being built correctly
    print(f"🔐 Headers: {headers}")  # Debug: Check if headers are correctly set

    try:
        # Fetch tickets from the external API
        res = make_request("GET", url, headers=headers, payload=None)  # Added method parameter
        print("📦 Raw API Response:", res)  # Debug: Print the raw API response to check for data

        # Extract tickets from the response
        tickets = res.get("data", [])
        print(f"🎟 Tickets ({len(tickets)}):", tickets)  # Debug: Check how many tickets were fetched

        # Loop through the tickets and insert them into Genie Ticket Log or update status
        for ticket in tickets:
            # Get the fields from the external ticket
            tittle = ticket.get("subject")
            description = ticket.get("description", "")
            status = ticket.get("status")
            raised_by = ticket.get("raised_by")

            # Remove HTML tags from the description
            clean_description = re.sub(r'<[^>]*>', '', description)  # Remove HTML tags

            # Check if the ticket already exists in the Genie Ticket Log (by ticket's subject)
            existing_ticket = frappe.get_all("Genie Ticket log", filters={"tittle": tittle}, limit=1)

            if existing_ticket:
                # Ticket already exists, update only the status field
                ticket_doc = frappe.get_doc("Genie Ticket log", existing_ticket[0].name)
                ticket_doc.status = status  # Update the status
                ticket_doc.save(ignore_permissions=True)  # Save the updated ticket
                print(f"🎫 Ticket with title '{tittle}' status updated to '{status}' in Genie Ticket Log")
            else:
                # Ticket doesn't exist, create a new record with all fields
                new_ticket = frappe.get_doc({
                    "doctype": "Genie Ticket log",
                    "tittle": tittle,
                    "description": clean_description,  # Use cleaned description
                    "status": status,
                    "raised_by": raised_by,
                })
                new_ticket.insert(ignore_permissions=True)  # Insert new ticket into Genie Ticket Log
                print(f"🎫 Ticket with title '{tittle}' inserted into Genie Ticket Log")

        frappe.msgprint(f"🎫 {len(tickets)} tickets fetched and stored in Genie Ticket Log")
        return {"status": "success", "ticket_count": len(tickets)}

    except Exception as e:
        print("❌ Error occurred:", str(e))  # Debug: Print the error message
        frappe.msgprint(f"❌ Error occurred: {str(e)}")
        return {"status": "error", "error": str(e)}

def make_request(method, url, headers=None, payload=None):
    if method == "GET":
        response = requests.get(url, headers=headers)
    elif method == "POST":
        response = requests.post(url, headers=headers, json=payload)
    else:
        raise Exception("Unsupported HTTP method")

    response.raise_for_status()
    return response.json()
