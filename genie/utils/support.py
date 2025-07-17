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
from urllib.parse import quote

@frappe.whitelist()
def sync_domain_tickets():
    current_site_url = "https://" + frappe.local.site
    settings = frappe.get_cached_doc("Genie Settings")

    headers = {
        "Authorization": f"token {settings.get_password('support_api_token')}",
        "Content-Type": "application/json",
    }

    filters = json.dumps([["custom_site_name", "=", current_site_url]])
    fields = json.dumps(["*"])
    url = f"{settings.support_url}/api/v2/document/HD Ticket?fields={quote(fields)}&filters={quote(filters)}"

    try:
        frappe.msgprint("🔄 Fetching HD Tickets...")
        res = make_request("GET", url, headers=headers)
        tickets = res.get("data", [])

        for ticket in tickets:
            tittle = ticket.get("subject")
            description = ticket.get("description", "")
            status = ticket.get("status")
            raised_by = ticket.get("raised_by")
            ticket_id = ticket.get("name")

            clean_description = re.sub(r'<[^>]*>', '', description)
            clean_description = clean_description.replace(current_site_url, "")
            clean_description = re.sub(r"\bDomain:?\b", "", clean_description, flags=re.IGNORECASE)
            clean_description = clean_description.replace(":", "").strip()

            # Start conversation layout
            conversation_html = '<div style="font-family:Arial,sans-serif;">'

            try:
                filters_json = json.dumps([
                    ["reference_doctype", "=", "HD Ticket"],
                    ["reference_name", "=", ticket_id]
                ])
                fields_json = json.dumps(["sender", "content"])

                comments_url = (
                    f"{settings.support_url}/api/resource/Communication"
                    f"?fields={quote(fields_json)}&filters={quote(filters_json)}"
                )
                comments_res = make_request("GET", comments_url, headers=headers)
                comments = comments_res.get("data", [])

                for index, msg in enumerate(comments):
                    sender = msg.get("sender", "Unknown")
                    content = msg.get("content", "")

                    # Override sender for first message to match raised_by
                    if index == 0:
                        sender = raised_by

                    # Clean content
                    content = content.replace(current_site_url, "")
                    content = re.sub(r"\bDomain:?\b", "", content, flags=re.IGNORECASE)
                    content = re.sub(r"\n", "<br>", content)

                    align = "right" if sender == raised_by else "left"
                    bg_color = "#d1f8d1" if sender == raised_by else "#f0f0f0"

                    conversation_html += f"""
                        <div style="text-align:{align}; margin:10px 0;">
                            <div style="display:inline-block; background:{bg_color}; color:#000; padding:10px 14px; border-radius:10px; max-width:75%;">
                                <div style="font-weight:bold; font-size:13px;">{sender}</div>
                                <div style="margin-top:5px;">{content.strip()}</div>
                            </div>
                        </div>
                    """

                conversation_html += "</div>"

            except Exception as ce:
                frappe.msgprint(f"⚠️ Error fetching comments for '{tittle}':<br>{str(ce)}")

            # Save ticket to Genie Ticket log
            existing_ticket_name = frappe.get_value("Genie Ticket log", {"tittle": tittle}, "name")

            if existing_ticket_name:
                frappe.msgprint(f"🔁 Updating ticket: {tittle}")
                ticket_doc = frappe.get_doc("Genie Ticket log", existing_ticket_name)
                ticket_doc.status = status
                ticket_doc.ticket_id = ticket_id
                ticket_doc.conversation_log = conversation_html
                ticket_doc.save(ignore_permissions=True)
            else:
                new_ticket = frappe.get_doc({
                    "doctype": "Genie Ticket log",
                    "tittle": tittle,
                    "description": clean_description,
                    "status": status,
                    "raised_by": raised_by,
                    "ticket_id": ticket_id,
                    "conversation_log": conversation_html
                })
                new_ticket.insert(ignore_permissions=True)

        return {"status": "success", "ticket_count": len(tickets)}

    except Exception as e:
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


@frappe.whitelist()
def send_ticket_reply(ticket_id, message):
    try:
        current_site_url = "https://" + frappe.local.site
        settings = frappe.get_cached_doc("Genie Settings")

        headers = {
            "Authorization": f"token {settings.get_password('support_api_token')}",
            "Content-Type": "application/json",
        }

        # ✅ 1. Fetch the ticket to get the real raised_by
        ticket_url = f"{settings.support_url}/api/resource/HD Ticket/{ticket_id}"
        ticket_response = requests.get(ticket_url, headers=headers)
        ticket_response.raise_for_status()

        ticket_data = ticket_response.json().get("data", {})
        raised_by = ticket_data["raised_by"]  # ✅ Must exist

        # ✅ 2. Send the reply, spoofing sender as raised_by
        payload = {
            "reference_doctype": "HD Ticket",
            "reference_name": ticket_id,
            "content": message,
            "sender": raised_by,  # ✅ Always use raised_by
            "sent_from_site": current_site_url
        }

        communication_url = f"{settings.support_url}/api/resource/Communication"
        reply_response = requests.post(communication_url, headers=headers, json=payload)
        reply_response.raise_for_status()

        return {"status": "success", "data": reply_response.json()}

    except Exception as e:
        frappe.log_error(f"❌ Error in send_ticket_reply: {str(e)}")
        return {"status": "error", "error": str(e)}
