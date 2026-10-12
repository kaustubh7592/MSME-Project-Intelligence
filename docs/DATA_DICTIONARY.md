# Data Dictionary

This file defines the first canonical fields. Add fields only when real source documents justify them. Missing values remain missing.

## Identity/classification
- `project_name`
- `project_alias`
- `project_type`: manufacturing | service | processing | agriculture_linked | mixed | unknown
- `sector`
- `subsector`
- `business_description`
- `source_document_year`
- `location_context`

## Financial/capital
- `total_project_cost_inr`
- `fixed_capital_inr`
- `land_cost_inr`
- `building_cost_inr`
- `machinery_cost_inr`
- `other_fixed_assets_inr`
- `working_capital_inr`
- `annual_revenue_inr`
- `annual_expense_inr`
- `annual_profit_inr`
- `break_even_percent`
- `payback_years`
- `irr_percent`
- `npv_inr`

## Operations
- `working_days_per_year`
- `shifts_per_day`
- `hours_per_shift`
- `capacity_utilization_percent`
- `annual_capacity_value`
- `annual_capacity_unit`
- `power_requirement_kw`
- `water_requirement`
- `fuel_requirement`
- `land_area_sqft`
- `built_up_area_sqft`

## Human resources
- `employee_count_total`
- `managerial_count`
- `skilled_worker_count`
- `unskilled_worker_count`
- `monthly_payroll_inr`
- `annual_payroll_inr`

## Repeating lists
Products, machinery, raw materials and role-level manpower details may be stored as structured JSON plus atomic facts for important query fields.

## Money normalization
Examples:
- `10 lakh` -> `1000000 INR`
- `Rs. 2.5 Lacs` -> `250000 INR`
- `1.2 crore` -> `12000000 INR`

Always store raw source text/value alongside normalized values.

## Evidence rule
Core numeric facts must reference source document + page and table/element when available.
