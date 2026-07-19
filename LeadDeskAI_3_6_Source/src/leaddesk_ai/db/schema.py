SCHEMA_VERSION = 9

SCHEMA_SQL = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS schema_meta(version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS properties(
 id INTEGER PRIMARY KEY, lead_code TEXT UNIQUE, market TEXT DEFAULT '', county TEXT DEFAULT '',
 address TEXT DEFAULT '', city TEXT DEFAULT '', state TEXT DEFAULT '', zip TEXT DEFAULT '', apn TEXT DEFAULT '',
 property_type TEXT DEFAULT '', bedrooms REAL, bathrooms REAL, square_feet REAL,
 source_file TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'New', priority TEXT NOT NULL DEFAULT 'Normal',
 follow_up_date TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS owners(
 id INTEGER PRIMARY KEY, property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
 name TEXT DEFAULT '', mailing_address TEXT DEFAULT '', mailing_city TEXT DEFAULT '', mailing_state TEXT DEFAULT '',
 mailing_zip TEXT DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS contacts(
 id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
 type TEXT NOT NULL CHECK(type IN ('phone','email')), value TEXT NOT NULL DEFAULT '', label TEXT DEFAULT '',
 is_clean INTEGER NOT NULL DEFAULT 0, is_primary INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS communication_preferences(
 id INTEGER PRIMARY KEY, property_id INTEGER UNIQUE NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
 call_allowed INTEGER NOT NULL DEFAULT 0, text_allowed INTEGER NOT NULL DEFAULT 0,
 email_allowed INTEGER NOT NULL DEFAULT 0, mail_allowed INTEGER NOT NULL DEFAULT 1,
 consent_source TEXT DEFAULT '', consent_date TEXT DEFAULT '', internal_dnc INTEGER NOT NULL DEFAULT 0,
 opt_out INTEGER NOT NULL DEFAULT 0, opt_out_reason TEXT DEFAULT '', updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notes(
 id INTEGER PRIMARY KEY, property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
 body TEXT NOT NULL, created_by TEXT DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS activities(
 id INTEGER PRIMARY KEY, property_id INTEGER REFERENCES properties(id) ON DELETE CASCADE,
 activity_type TEXT NOT NULL, details TEXT DEFAULT '', created_by TEXT DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks(
 id INTEGER PRIMARY KEY, property_id INTEGER REFERENCES properties(id) ON DELETE CASCADE,
 title TEXT NOT NULL, due_date TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'Open',
 priority TEXT NOT NULL DEFAULT 'Normal', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS comparable_sales(
 id INTEGER PRIMARY KEY, property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
 address TEXT NOT NULL, sold_price REAL NOT NULL DEFAULT 0, sold_date TEXT DEFAULT '', square_feet REAL,
 distance_miles REAL, bedrooms REAL, bathrooms REAL, lot_size REAL, condition_notes TEXT DEFAULT '', source TEXT DEFAULT '',
 verified INTEGER NOT NULL DEFAULT 0, selected INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS repair_estimates(
 id INTEGER PRIMARY KEY, property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
 category TEXT NOT NULL, description TEXT DEFAULT '', amount REAL NOT NULL DEFAULT 0,
 source TEXT DEFAULT '', verified INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS title_checks(
 id INTEGER PRIMARY KEY, property_id INTEGER UNIQUE NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
 ownership_verified INTEGER NOT NULL DEFAULT 0, deed_reviewed INTEGER NOT NULL DEFAULT 0,
 taxes_checked INTEGER NOT NULL DEFAULT 0, liens_preliminary_checked INTEGER NOT NULL DEFAULT 0,
 professional_title_ordered INTEGER NOT NULL DEFAULT 0, title_clear INTEGER NOT NULL DEFAULT 0,
 title_company TEXT DEFAULT '', notes TEXT DEFAULT '', updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS deals(
 id INTEGER PRIMARY KEY, property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
 arv REAL NOT NULL DEFAULT 0, repairs REAL NOT NULL DEFAULT 0, target_pct REAL NOT NULL DEFAULT .70,
 wholesale_fee REAL NOT NULL DEFAULT 10000, closing_costs REAL NOT NULL DEFAULT 0,
 holding_costs REAL NOT NULL DEFAULT 0, buyer_price REAL NOT NULL DEFAULT 0, purchase_price REAL NOT NULL DEFAULT 0,
 marketing_costs REAL NOT NULL DEFAULT 0, misc_costs REAL NOT NULL DEFAULT 0,
 mao REAL NOT NULL DEFAULT 0, total_investment REAL NOT NULL DEFAULT 0, projected_profit REAL NOT NULL DEFAULT 0,
 roi REAL NOT NULL DEFAULT 0, deal_score TEXT NOT NULL DEFAULT 'Marginal',
 status TEXT NOT NULL DEFAULT 'Analyzing', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS buyers(
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, company TEXT DEFAULT '', email TEXT DEFAULT '', phone TEXT DEFAULT '',
 markets TEXT DEFAULT '', property_types TEXT DEFAULT '', min_price REAL, max_price REAL,
 rehab_level TEXT DEFAULT '', funding_type TEXT DEFAULT '', zip_codes TEXT DEFAULT '', counties TEXT DEFAULT '',
 avg_close_days INTEGER, active INTEGER NOT NULL DEFAULT 1, notes TEXT DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS buyer_offers(
 id INTEGER PRIMARY KEY, property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
 buyer_id INTEGER REFERENCES buyers(id) ON DELETE SET NULL, amount REAL NOT NULL DEFAULT 0,
 proof_of_funds INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'New', notes TEXT DEFAULT '', sent_date TEXT DEFAULT '', responded_date TEXT DEFAULT '',
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS offer_scenarios(
 id INTEGER PRIMARY KEY, property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
 suggested_arv REAL NOT NULL DEFAULT 0, seller_offer REAL NOT NULL DEFAULT 0,
 buyer_price REAL NOT NULL DEFAULT 0, assignment_fee REAL NOT NULL DEFAULT 0,
 estimated_profit REAL NOT NULL DEFAULT 0, notes TEXT DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS campaigns(
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, channel TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Draft',
 total_records INTEGER NOT NULL DEFAULT 0, cost REAL NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log(
 id INTEGER PRIMARY KEY, user_name TEXT DEFAULT '', action TEXT NOT NULL, entity_type TEXT DEFAULT '',
 entity_id INTEGER, before_json TEXT DEFAULT '', after_json TEXT DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS app_events(
 id INTEGER PRIMARY KEY, event_name TEXT NOT NULL, payload_json TEXT DEFAULT '{}', created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_properties_address ON properties(address,city,state,zip);
CREATE INDEX IF NOT EXISTS idx_contacts_value ON contacts(value);
CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(status,due_date);
CREATE INDEX IF NOT EXISTS idx_comps_property ON comparable_sales(property_id);
CREATE INDEX IF NOT EXISTS idx_offers_property ON offer_scenarios(property_id,id);
"""
