"""Default classification guidance extracted from the governing URS artifact."""

import json

URS_TEMPLATE_CATALOG: dict[str, list[object]] = json.loads(r"""{
  "categories": [
    {
      "id": 1,
      "name": "Capacity",
      "icon": "ti-building-factory",
      "active": true,
      "applies": "Both",
      "subs": [
        {
          "name": "Debottlenecking / OTIF Improvement",
          "titleTemplate": "Throughput Improvement of [Product] from [X] [Unit] to [Y] [Unit]",
          "problem": "Production throughput constrained by bottleneck operations causing delays in order fulfilment and poor OTIF",
          "solution": "Identify and eliminate binding constraint using Theory of Constraints; balance line capacities; improve scheduling",
          "kpi": "Throughput (MT/day) / OTIF % / Capacity utilisation %",
          "area": "Production / Planning / Dispatch"
        },
        {
          "name": "Line Balancing",
          "titleTemplate": "Line Balancing Improvement of [Line/Process] to reduce idle time from [X]% to [Y]%",
          "problem": "Uneven workload across workstations causing bottlenecks, idle time and underutilisation of capacity",
          "solution": "Time study, redistribute tasks to balance cycle times, eliminate non-value-add steps across all stations",
          "kpi": "OEE / Throughput (units/hr) / Idle time %",
          "area": "Production / Industrial Engineering"
        },
        {
          "name": "Machine Uptime Improvement",
          "titleTemplate": "Machine Uptime Improvement of [Equipment] from [X]% to [Y]%",
          "problem": "Frequent breakdowns and unplanned downtime reducing available production capacity below target",
          "solution": "Implement preventive maintenance schedule, spare parts management programme, root cause elimination of top failures",
          "kpi": "MTBF (hrs) / Machine availability % / Breakdown frequency",
          "area": "Maintenance / Production"
        },
        {
          "name": "Throughput Enhancement",
          "titleTemplate": "Throughput Enhancement of [Line/Product] from [X] units/day to [Y] units/day",
          "problem": "Output consistently below designed capacity due to system constraints, speed losses or yield gaps",
          "solution": "Identify binding constraint using Theory of Constraints, systematically eliminate with focused improvement actions",
          "kpi": "Units/hr / OEE % / Capacity utilisation %",
          "area": "Operations / Engineering"
        },
        {
          "name": "Shift Utilisation",
          "titleTemplate": "Shift Utilisation Improvement of [Area] from [X]% to [Y]%",
          "problem": "Low productivity during shift changeovers, poor handover discipline causing significant production time loss",
          "solution": "Standardise handover process with structured overlap window, digital checklist and cross-training programme",
          "kpi": "OEE / Labour efficiency % / Changeover time (min)",
          "area": "Production / HR"
        }
      ]
    },
    {
      "id": 2,
      "name": "OPEX",
      "icon": "ti-coins",
      "active": true,
      "applies": "Both",
      "subs": [
        {
          "name": "OEE / Cycle Time Reduction",
          "titleTemplate": "OEE Improvement of [Equipment/Line] from [X]% to [Y]%",
          "problem": "Overall Equipment Effectiveness below target due to availability, performance or quality losses causing high cost per unit",
          "solution": "Structured OEE improvement programme targeting top losses — planned downtime reduction, speed losses and first-pass quality",
          "kpi": "OEE % / Cycle time (sec) / Units per hour",
          "area": "Production / Maintenance / Engineering"
        },
        {
          "name": "ETP Cost Reduction",
          "titleTemplate": "ETP Operating Cost Reduction from ₹[X]/KL to ₹[Y]/KL",
          "problem": "Effluent Treatment Plant operating costs are high due to chemical overdosing, high energy use or frequent sludge disposal",
          "solution": "Optimise chemical dosing through jar testing, install energy-efficient aeration, reduce sludge generation at source",
          "kpi": "ETP cost ₹/KL treated / Chemical consumption / Energy kWh",
          "area": "ETP / EHS / Utilities"
        },
        {
          "name": "Repair and Maintenance Cost",
          "titleTemplate": "R&M Cost Reduction from ₹[X]L/month to ₹[Y]L/month",
          "problem": "R&M spend above budget due to reactive maintenance, high spare parts cost or frequent unplanned breakdowns",
          "solution": "Implement planned preventive maintenance, build in-house repair capability, optimise spare parts with criticality analysis",
          "kpi": "R&M cost ₹/month / R&M as % of asset value",
          "area": "Maintenance / Engineering"
        },
        {
          "name": "Breakdown Reduction",
          "titleTemplate": "Breakdown Reduction of [Equipment] from [X] incidents/month to [Y] incidents/month",
          "problem": "Frequent unplanned equipment breakdowns causing production loss and high repair costs",
          "solution": "Root cause analysis of top breakdown codes, FMEA-based preventive actions, improve lubrication and inspection routines",
          "kpi": "MTBF (hours) / MTTR (hours) / Breakdown frequency",
          "area": "Maintenance / Production"
        },
        {
          "name": "Consumables Cost or Usage Reduction",
          "titleTemplate": "Consumable Cost Reduction of [Item] from ₹[X]/unit to ₹[Y]/unit",
          "problem": "Consumable usage (gloves, filters, lab chemicals, cleaning agents) excessive and not tracked against norms",
          "solution": "Establish item-wise usage norms, implement issue-against-job controls, identify substitutes",
          "kpi": "Consumable cost ₹/unit produced / Variance vs norm %",
          "area": "Operations / Maintenance / Lab"
        },
        {
          "name": "QC Testing Cost Reduction",
          "titleTemplate": "QC Testing Cost Reduction from ₹[X]/batch to ₹[Y]/batch",
          "problem": "Quality control testing costs high due to over-testing, expensive external labs or inefficient in-house methods",
          "solution": "Risk-based testing frequency optimisation, invest in in-house testing capability, batch release on process control data",
          "kpi": "QC cost ₹/batch / Test turnaround time / External lab spend ₹",
          "area": "Quality / Laboratory"
        },
        {
          "name": "Admin Cost Reduction",
          "titleTemplate": "Admin Overhead Reduction from ₹[X]L/month to ₹[Y]L/month",
          "problem": "Administrative and overhead costs not benchmarked — stationery, printing, travel, communication spend is high",
          "solution": "Digitise approvals and reports, set travel policies, consolidate vendors, move to cloud-based tools",
          "kpi": "Admin cost ₹/month / Cost per employee / Overhead %",
          "area": "Admin / Finance / HR"
        },
        {
          "name": "Quality Improvement",
          "titleTemplate": "Defect Reduction of [Product/Process] from [X] PPM to [Y] PPM",
          "problem": "High defect rates, customer complaints or rework costs impacting profitability and customer satisfaction",
          "solution": "SPC implementation, mistake-proofing (poka-yoke), process standardisation and CAPA on top defect codes",
          "kpi": "Defect PPM / First pass yield % / Customer complaints/month",
          "area": "Quality / Operations"
        },
        {
          "name": "Services Cost Reduction",
          "titleTemplate": "Service Cost Reduction of [Service Type] from ₹[X]L/month to ₹[Y]L/month",
          "problem": "Third-party service costs (housekeeping, security, contract labour, transport) above market rates or not optimised",
          "solution": "Re-tender services with clear SLAs, consolidate providers, explore shared services model, benchmark market",
          "kpi": "Service cost ₹/month / Cost per service unit / Savings ₹",
          "area": "Procurement / Admin / HR"
        },
        {
          "name": "Service Level Agreement (SLA) Improvement",
          "titleTemplate": "SLA Adherence Improvement for [Vendor/Service] from [X]% to [Y]%",
          "problem": "Vendor or internal SLAs consistently missed causing production delays, quality issues or customer dissatisfaction",
          "solution": "Define measurable SLA metrics, monthly vendor performance reviews, penalty/incentive clauses and escalation protocols",
          "kpi": "SLA adherence % / Response time / Downtime due to SLA breach",
          "area": "Procurement / Operations / Admin"
        },
        {
          "name": "Digital / Automation / IT",
          "titleTemplate": "Digitisation of [Process] to reduce [Metric] from [X] to [Y]",
          "problem": "Manual processes, paper-based records and siloed data causing errors, delays and poor decision visibility",
          "solution": "Implement MES, IoT sensors, RPA for repetitive tasks, ERP modules, digital dashboards for real-time monitoring",
          "kpi": "Process cycle time / Error rate / Report turnaround time",
          "area": "IT / Operations / Engineering"
        },
        {
          "name": "Procedure / Process Simplification",
          "titleTemplate": "Process Lead Time Reduction of [Process] from [X] days to [Y] days",
          "problem": "Overly complex procedures, redundant approvals and multiple handoffs causing delays and non-value-add time",
          "solution": "Process mapping, elimination of non-value-add steps, simplification of approval workflows, standardisation",
          "kpi": "Process lead time / Steps per process / Compliance rate %",
          "area": "Operations / Quality / Admin"
        },
        {
          "name": "Legal Compliance",
          "titleTemplate": "Compliance Score Improvement for [Regulation/Area] from [X]% to [Y]%",
          "problem": "Gaps in legal and regulatory compliance creating risk of penalties, licence revocation or reputational damage",
          "solution": "Compliance calendar, legal audit, training programme, automation of compliance tracking and reporting",
          "kpi": "Compliance % / Open observations / Penalty ₹ / Audit score",
          "area": "Legal / EHS / Admin / Finance"
        },
        {
          "name": "Services",
          "titleTemplate": "Service Quality Improvement of [Service] from [X] score to [Y] score",
          "problem": "Service delivery quality or cost-effectiveness suboptimal in canteen, transport, clinic or guest house",
          "solution": "Define service standards, employee satisfaction surveys, benchmark costs and renegotiate with service providers",
          "kpi": "Employee satisfaction score / Service cost ₹/head / Quality score",
          "area": "Admin / HR / Finance"
        },
        {
          "name": "Water Saving",
          "titleTemplate": "Water Consumption Reduction from [X] kL/unit to [Y] kL/unit",
          "problem": "Water consumption per unit of production high, leading to high utility cost and environmental impact",
          "solution": "Identify water loss points, implement water recycling, install flow meters, optimise cooling tower makeup water",
          "kpi": "Water consumption kL/unit / Water cost ₹/month / Recycling %",
          "area": "Utilities / EHS / Production"
        },
        {
          "name": "Overhead Reduction",
          "titleTemplate": "Overhead Cost Reduction of [Area/Function] from ₹[X]L to ₹[Y]L/month",
          "problem": "High fixed overheads significantly reducing profitability per unit — not benchmarked against industry",
          "solution": "Identify and eliminate non-value-add costs using Activity-Based Costing, zero-based budgeting exercise",
          "kpi": "Cost per unit / Overhead % of revenue / Savings ₹/yr",
          "area": "Finance / Operations"
        },
        {
          "name": "Contract Renegotiation",
          "titleTemplate": "Contract Cost Reduction of [Vendor/Service] from ₹[X]L to ₹[Y]L/yr",
          "problem": "Above-market rates on service, utility and logistics contracts due to legacy pricing and lack of benchmarking",
          "solution": "Benchmark market rates thoroughly, consolidate vendors, renegotiate with volume leverage and multi-year LTAs",
          "kpi": "Cost saving ₹ per year / Savings % vs previous contract",
          "area": "Procurement / Finance"
        },
        {
          "name": "Others",
          "titleTemplate": "Cost Saving of [Area/Process] from ₹[X]L to ₹[Y]L per [Period]",
          "problem": "Operational cost improvement opportunity not covered under standard OPEX subcategories",
          "solution": "Define specific problem, quantify baseline, implement targeted solution and track savings against baseline",
          "kpi": "Cost saving ₹ / Relevant operational metric",
          "area": "As applicable"
        }
      ]
    },
    {
      "id": 3,
      "name": "Material",
      "icon": "ti-package",
      "active": true,
      "applies": "Both",
      "subs": [
        {
          "name": "Yield Improvement",
          "titleTemplate": "Yield Improvement of [Product] from [X]% to [Y]%",
          "problem": "Material yield below theoretical or benchmark levels causing high raw material cost per unit of output",
          "solution": "Optimise reaction conditions, reduce sampling losses, improve first-fill accuracy, minimise hold-up volumes",
          "kpi": "Yield % (actual vs theoretical) / RM cost per unit ₹",
          "area": "Production / Process / R&D"
        },
        {
          "name": "Raw Material Yield Improvement",
          "titleTemplate": "Raw Material Yield of [RM/Product] from [X]% to [Y]%",
          "problem": "Excessive raw material waste during processing due to suboptimal process parameters, handling losses or specification gaps",
          "solution": "Process parameter optimisation, precision weighing, reduce spillage and handling losses at every transfer point",
          "kpi": "Yield % / Scrap cost ₹/month / RM cost per unit",
          "area": "Process / Quality / Production"
        },
        {
          "name": "BOM Optimization",
          "titleTemplate": "BOM Material Cost Reduction of [Product] from ₹[X]/unit to ₹[Y]/unit",
          "problem": "Bill of Materials contains over-specified or redundant materials increasing standard material cost unnecessarily",
          "solution": "Technical review of BOM with R&D and production, value engineering to substitute or eliminate materials",
          "kpi": "Standard material cost ₹/unit / BOM variance / Savings ₹",
          "area": "R&D / Production / Procurement"
        },
        {
          "name": "Backward Integration",
          "titleTemplate": "Backward Integration of [Material] to reduce cost from ₹[X]/kg to ₹[Y]/kg",
          "problem": "Key raw materials sourced externally at high cost where in-house production is technically and commercially viable",
          "solution": "Feasibility study for captive production, evaluate make vs buy, pilot batch and scale up if viable",
          "kpi": "RM cost savings ₹/year / Self-sufficiency % / Payback period",
          "area": "Production / R&D / Finance / Procurement"
        },
        {
          "name": "Catalyst Recovery",
          "titleTemplate": "Catalyst Recovery Improvement from [X]% to [Y]%",
          "problem": "Spent catalyst disposed rather than recovered, causing high catalyst cost and hazardous waste generation",
          "solution": "Implement catalyst recovery, regeneration or recycling; explore vendor take-back for precious metal catalysts",
          "kpi": "Catalyst recovery % / Catalyst cost ₹/batch / Waste reduction kg",
          "area": "Production / R&D / EHS"
        },
        {
          "name": "COPQ Improvement",
          "titleTemplate": "Cost of Poor Quality Reduction from ₹[X]L/month to ₹[Y]L/month",
          "problem": "Cost of Poor Quality (rejections, rework, returns, testing, complaints) is high and not systematically tracked",
          "solution": "COPQ measurement framework, structured CAPA on top rejection codes, process capability improvement",
          "kpi": "COPQ ₹/month / Rejection rate % / Customer returns / RFT %",
          "area": "Quality / Production / Procurement"
        },
        {
          "name": "Raw Material Consumption / Cost Reduction",
          "titleTemplate": "Raw Material Cost Reduction of [RM Name] from ₹[X]/unit to ₹[Y]/unit",
          "problem": "Raw material consumption per unit above standard due to process inefficiencies, measurement errors or specification issues",
          "solution": "Usage norm setting, consumption monitoring, process parameter optimisation, alternate RM qualification",
          "kpi": "RM consumption per unit / RM cost ₹/unit / Variance vs norm %",
          "area": "Production / Procurement / R&D"
        },
        {
          "name": "Packing Material Consumption / Cost Reduction",
          "titleTemplate": "Packing Material Cost Reduction from ₹[X]/unit to ₹[Y]/unit",
          "problem": "Packing material usage and cost high due to over-specification, damage, pilferage or non-standard usage",
          "solution": "Right-size packing specifications, implement usage norms, reduce handling damage, explore reusable packaging",
          "kpi": "PM cost ₹/unit packed / PM consumption / Damage %",
          "area": "Packing / Production / Procurement"
        },
        {
          "name": "Solvent Recovery / Recycle / Reuse",
          "titleTemplate": "Solvent Recovery Improvement of [Solvent] from [X]% to [Y]%",
          "problem": "Solvents used once and sent to waste/disposal resulting in high solvent cost and hazardous waste volume",
          "solution": "Install solvent recovery distillation, implement closed-loop recycling, qualify recovered solvent for reuse",
          "kpi": "Solvent recovery % / Solvent cost ₹/batch / Hazardous waste kg",
          "area": "Production / EHS / R&D / Engineering"
        },
        {
          "name": "Waste Elimination / Reduction / Recycle / Reuse",
          "titleTemplate": "Waste Generation Reduction from [X] kg/unit to [Y] kg/unit",
          "problem": "Process and non-process waste generation high, increasing disposal costs and environmental liability",
          "solution": "Waste minimisation at source, segregation at generation point, internal recycling, co-processing or vendor recycling",
          "kpi": "Waste generation kg/unit / Disposal cost ₹/month / Recycling %",
          "area": "EHS / Production / Procurement"
        },
        {
          "name": "Inventory Reduction",
          "titleTemplate": "Inventory Reduction of [Material/Product] from [X] days to [Y] days",
          "problem": "Excess WIP and finished goods tying up working capital and occupying expensive warehouse space",
          "solution": "Implement pull system with kanban and reorder point triggers based on actual demand signals",
          "kpi": "Inventory days / WIP days outstanding / Inventory turns",
          "area": "Supply Chain / Finance"
        },
        {
          "name": "Supplier Quality Improvement",
          "titleTemplate": "Incoming Rejection Rate of [Supplier/Material] from [X]% to [Y]%",
          "problem": "Incoming material rejections causing line stoppages, rework costs and production schedule disruption",
          "solution": "Supplier development programme with SPC at source, incoming inspection protocols and CAPA review meetings",
          "kpi": "Incoming PPM / Rejection rate % / Supplier quality score",
          "area": "Quality / Procurement"
        },
        {
          "name": "Material Handling",
          "titleTemplate": "Material Handling Loss Reduction of [Material] from [X]% to [Y]%",
          "problem": "Excessive material movement, handling damage and loss causing increased cost and safety risk",
          "solution": "Redesign material flow layout with visual management, dedicated lanes and handling equipment upgrades",
          "kpi": "Handling loss % / Damage cost ₹/month / Material movement distance",
          "area": "Warehouse / Production"
        },
        {
          "name": "Others",
          "titleTemplate": "Material Cost Saving of [Area/Material] from ₹[X] to ₹[Y] per [Period]",
          "problem": "Material saving opportunity not covered under standard Material subcategories",
          "solution": "Define specific problem, establish baseline material consumption, implement targeted solution",
          "kpi": "Material cost saving ₹ / Relevant consumption metric",
          "area": "As applicable"
        }
      ]
    },
    {
      "id": 4,
      "name": "ESG / ENCON",
      "icon": "ti-leaf",
      "active": true,
      "applies": "Both",
      "subs": [
        {
          "name": "Energy Conservation (Power / Fuel)",
          "titleTemplate": "Energy Consumption Reduction of [Utility/Equipment] from [X] kWh/unit to [Y] kWh/unit",
          "problem": "Energy consumption per unit above benchmark or rising, increasing production cost and carbon footprint",
          "solution": "Energy audit, install VFDs, LED lighting, heat recovery systems, optimise compressed air, switch to renewables",
          "kpi": "Energy kWh or GJ/unit / Energy cost ₹/unit / CO₂ kg/unit",
          "area": "Utilities / Engineering / Production"
        },
        {
          "name": "Electricity Consumption Reduction",
          "titleTemplate": "Electricity Consumption Reduction from [X] kWh/unit to [Y] kWh/unit",
          "problem": "High electricity consumption per unit output inflating production cost and increasing carbon footprint",
          "solution": "Install VFDs on motors, LED lighting retrofit, power factor correction, optimise compressed air system",
          "kpi": "kWh/unit / Energy cost ₹/unit / Power factor",
          "area": "Utilities / Engineering"
        },
        {
          "name": "Compressed Air Leakage Reduction",
          "titleTemplate": "Compressed Air Loss Reduction from [X]% to [Y]%",
          "problem": "Significant air leaks wasting energy across the plant compressed air network",
          "solution": "Systematic leak detection using ultrasonic detector, rapid rectification programme, pressure optimisation",
          "kpi": "Air system loss % / kWh savings/month / Compressor load %",
          "area": "Maintenance / Utilities"
        },
        {
          "name": "Steam / Heat Recovery",
          "titleTemplate": "Steam / Heat Recovery Improvement from [X]% to [Y]%",
          "problem": "Waste heat and steam condensate being vented without energy recovery, increasing fuel cost",
          "solution": "Install heat exchangers, condensate recovery system, insulation improvements on steam lines",
          "kpi": "Steam consumption kg/unit / GJ saved / Condensate recovery %",
          "area": "Utilities / Engineering"
        },
        {
          "name": "Renewable Energy",
          "titleTemplate": "Renewable Energy Share Improvement from [X]% to [Y]% of total consumption",
          "problem": "High dependence on grid power at peak tariff rates inflating energy cost significantly",
          "solution": "Solar rooftop installation or captive renewable energy procurement arrangement (PPA)",
          "kpi": "Renewable energy % share / ₹/unit saved / CO₂ reduction kg",
          "area": "Engineering / Finance / Utilities"
        },
        {
          "name": "Safety Improvement",
          "titleTemplate": "Near-Miss / Incident Reduction from [X] incidents/month to [Y] incidents/month",
          "problem": "Near-miss incidents, unsafe acts or unsafe conditions present risk of injury, loss of life or regulatory action",
          "solution": "Engineering controls, safety interlocks, ergonomic improvements, structured safety observation programme",
          "kpi": "Near-miss count / LTI frequency rate / TRIR / Safety observation score",
          "area": "EHS / Operations / Engineering"
        },
        {
          "name": "Carbon Footprint Reduction",
          "titleTemplate": "CO₂ Emissions Reduction from [X] kg/unit to [Y] kg/unit",
          "problem": "Carbon footprint per unit of production above regulatory threshold or sustainability target",
          "solution": "Energy efficiency measures, fuel switching, process optimisation, renewable energy adoption",
          "kpi": "CO₂ kg/unit / Scope 1 & 2 emissions (tCO₂e) / GHG intensity",
          "area": "EHS / Engineering / Utilities"
        },
        {
          "name": "Water Conservation",
          "titleTemplate": "Water Consumption Reduction from [X] kL/unit to [Y] kL/unit",
          "problem": "Water consumption per unit above benchmark, increasing cost and environmental regulatory risk",
          "solution": "Water audit, recycling infrastructure, closed-loop cooling, rainwater harvesting, reduce process water use",
          "kpi": "Water kL/unit / Water cost ₹/month / Recycling %",
          "area": "Utilities / EHS / Production"
        },
        {
          "name": "Waste Reduction / Zero Liquid Discharge",
          "titleTemplate": "Hazardous Waste Reduction from [X] kg/unit to [Y] kg/unit",
          "problem": "High hazardous waste generation increasing disposal cost and creating environmental compliance risk",
          "solution": "Waste minimisation at source, solvent recovery, co-processing with cement kilns, ZLD implementation",
          "kpi": "Waste kg/unit / Disposal cost ₹/month / ZLD compliance %",
          "area": "EHS / Production / Engineering"
        }
      ]
    },
    {
      "id": 5,
      "name": "Productivity Excellence",
      "icon": "ti-trending-up",
      "active": true,
      "applies": "Both",
      "subs": [
        {
          "name": "Productivity Improvement",
          "titleTemplate": "Productivity Improvement of [Line/Equipment] from [X] units/hr to [Y] units/hr",
          "problem": "Labour or equipment productivity below benchmark — output per person-hour or per machine-hour is low",
          "solution": "Time-motion study, eliminate non-value-add activities, implement 5S, standardise best operating practices",
          "kpi": "Output per person-hour / OEE % / Labour cost per unit ₹",
          "area": "Production / IE / HR / Operations"
        },
        {
          "name": "Labour Productivity",
          "titleTemplate": "Labour Productivity Improvement of [Area/Process] from [X] to [Y] units/person-hr",
          "problem": "Low output per person due to non-value-add motion, waiting and transportation waste across operations",
          "solution": "Motion study, ergonomics improvement and waste elimination using 5S and SMED methods",
          "kpi": "Units per person-hour / Labour cost per unit / Labour efficiency %",
          "area": "Operations / Industrial Engineering"
        },
        {
          "name": "Process Automation",
          "titleTemplate": "Automation of [Process/Task] to reduce cycle time from [X] min to [Y] min",
          "problem": "Manual repetitive tasks slowing throughput, introducing human error and limiting scalability",
          "solution": "Automate using collaborative robotics, PLC programming or RPA for back-office and shop-floor tasks",
          "kpi": "Cycle time reduction % / Error rate reduction / Headcount saving",
          "area": "Engineering / IT / Operations"
        },
        {
          "name": "Downtime Reduction",
          "titleTemplate": "Unplanned Downtime Reduction of [Line/Equipment] from [X] hrs/month to [Y] hrs/month",
          "problem": "Frequent unplanned stoppages breaking production flow and reducing OEE significantly below target",
          "solution": "Root cause analysis using FMEA and structured CAPA on top downtime loss codes",
          "kpi": "MTTR (hrs) / OEE % / Total downtime hrs/month",
          "area": "Maintenance / Production"
        },
        {
          "name": "Changeover Reduction (SMED)",
          "titleTemplate": "Changeover Time Reduction of [Equipment/Line] from [X] min to [Y] min",
          "problem": "Long changeover times between products reducing effective machine utilisation and scheduling flexibility",
          "solution": "Apply Single Minute Exchange of Die methodology with internal/external activity separation and standardisation",
          "kpi": "Changeover time (min) / Number of changeovers/month / OEE %",
          "area": "Production / Industrial Engineering"
        },
        {
          "name": "5S / Workplace Organisation",
          "titleTemplate": "5S Score Improvement of [Area/Department] from [X] to [Y] (out of 5)",
          "problem": "Disorganised workplaces causing time loss in searching, unsafe conditions and reduced quality focus",
          "solution": "Implement 5S programme (Sort, Set in order, Shine, Standardise, Sustain) with weekly audits and scoring",
          "kpi": "5S audit score / Search time reduction / Incident rate",
          "area": "Operations / EHS / All Departments"
        },
        {
          "name": "PPV / Purchase Price Variance",
          "titleTemplate": "Purchase Price Reduction of [Material/Service] from ₹[X] to ₹[Y] per unit",
          "problem": "Purchase prices above market rate due to single sourcing, lack of benchmarking or expired contracts",
          "solution": "Alternate vendor development, volume consolidation, specification optimisation, long-term agreements",
          "kpi": "PPV ₹ savings / Price reduction % / Vendor count",
          "area": "Procurement / Finance"
        },
        {
          "name": "Alternate Vendor Development",
          "titleTemplate": "Alternate Vendor Qualification for [Material] to reduce price from ₹[X] to ₹[Y]/unit",
          "problem": "Single-source supply dependency at premium price point creating supply risk and limiting negotiation leverage",
          "solution": "Qualify alternate suppliers through technical approval process to create competition and supply security",
          "kpi": "PPV ₹ savings / Number of qualified vendors / Supply risk score",
          "area": "Procurement / Quality"
        },
        {
          "name": "Volume Consolidation",
          "titleTemplate": "Volume Consolidation Saving of [Category] from ₹[X]L to ₹[Y]L/yr",
          "problem": "Fragmented purchases across plants and departments losing collective volume leverage with key suppliers",
          "solution": "Consolidate spend across all sites, negotiate bundled price with key suppliers, standardise specifications",
          "kpi": "Price reduction % / PPV ₹ savings / Vendor rationalisation",
          "area": "Procurement / Corporate"
        },
        {
          "name": "Specification Optimisation",
          "titleTemplate": "Specification Right-sizing of [Material] to reduce cost from ₹[X] to ₹[Y]/unit",
          "problem": "Over-specification of materials inflating material cost beyond actual functional requirements",
          "solution": "Value engineering exercise with R&D and production to right-size specs to actual functional requirements",
          "kpi": "Cost reduction ₹ / Number of spec changes / Quality impact",
          "area": "Engineering / Procurement / R&D"
        }
      ]
    },
    {
      "id": 6,
      "name": "Others",
      "icon": "ti-dots-circle-horizontal",
      "active": true,
      "applies": "Both",
      "subs": [
        {
          "name": "Inventory Optimization / Working Capital Reduction",
          "titleTemplate": "Inventory Reduction of [Material/Product] from [X] days to [Y] days",
          "problem": "Excess raw material, WIP or finished goods inventory tying up working capital and increasing carrying costs",
          "solution": "Implement demand-driven replenishment, set safety stock norms, reduce procurement cycle time",
          "kpi": "Inventory days / Working capital ₹ / Carrying cost ₹/month / Turns",
          "area": "Supply Chain / Finance / Production / Procurement"
        },
        {
          "name": "Safety Improvement",
          "titleTemplate": "Safety Incident Reduction of [Area] from [X] incidents/yr to [Y] incidents/yr",
          "problem": "Near-miss incidents or unsafe conditions creating risk on the shopfloor and regulatory exposure",
          "solution": "Engineering controls, safety proofing devices and structured safety awareness and observation programme",
          "kpi": "Near-miss count / LTI frequency rate / TRIR",
          "area": "EHS / Operations"
        },
        {
          "name": "Quality Improvement",
          "titleTemplate": "Quality Defect Reduction of [Product/Process] from [X] PPM to [Y] PPM",
          "problem": "High defect rate or customer complaint volume impacting customer satisfaction and CoQ",
          "solution": "SPC implementation, mistake-proofing (poka-yoke) and process standardisation programme",
          "kpi": "Defect PPM / DPHU / Customer complaints/month",
          "area": "Quality / Operations"
        },
        {
          "name": "Sustainability / ESG",
          "titleTemplate": "Sustainability Improvement of [Metric] from [X] to [Y] per unit",
          "problem": "High carbon footprint, water usage and waste generation per unit impacting ESG ratings",
          "solution": "Waste reduction, recycling infrastructure and circular economy initiatives",
          "kpi": "CO₂ kg/unit / Waste kg/unit / Water kL/unit",
          "area": "EHS / Operations"
        },
        {
          "name": "Digital / IT Improvement",
          "titleTemplate": "Digital Transformation of [Process] to reduce [Metric] from [X] to [Y]",
          "problem": "Manual data collection causing reporting delays, errors and poor operational visibility",
          "solution": "Digitise data capture using MES, IoT sensors or analytics dashboards for real-time decisions",
          "kpi": "Report turnaround time / Data accuracy % / Decision lag",
          "area": "IT / Operations"
        },
        {
          "name": "Long-term Agreements (LTA)",
          "titleTemplate": "LTA Cost Saving of [Vendor/Category] from ₹[X]L to ₹[Y]L/yr",
          "problem": "Spot buying at volatile market prices creating cost unpredictability and budget overruns",
          "solution": "Negotiate multi-year LTAs with price protection, escalation caps and volume guarantees",
          "kpi": "Price stability index / Annual PPV ₹ / Budget variance",
          "area": "Procurement / Finance"
        },
        {
          "name": "Others",
          "titleTemplate": "Improvement of [Area/Metric] from [X] to [Y]",
          "problem": "Improvement opportunity not covered under standard categories",
          "solution": "Define specific problem, quantify baseline, implement targeted solution and track results",
          "kpi": "Relevant metric",
          "area": "As applicable"
        }
      ]
    }
  ],
  "processAreas": [
    "Reactor / Synthesis Area",
    "Distillation / Purification Unit",
    "ETP / Effluent Treatment Plant",
    "Utility Block (Boiler, Chiller, Compressor)",
    "Electrical Substation",
    "Raw Material Storage / Warehouse",
    "Finished Goods Warehouse",
    "Quality Control Laboratory",
    "Dispatch / Logistics Dock",
    "Production Line 1",
    "Production Line 2",
    "Production Line 3",
    "Production Line 4",
    "Production Line 5",
    "Press Shop",
    "Fabrication Shop",
    "Assembly Line",
    "Packing Line",
    "Maintenance Workshop",
    "IT / Server Room",
    "Canteen / Cafeteria",
    "Administration Office",
    "HR Department",
    "Finance & Accounts",
    "Procurement / Purchase",
    "Supply Chain Management",
    "Engineering / Projects",
    "EHS / Safety",
    "R&D / Development Lab",
    "Quality Assurance",
    "Customer Service / Sales",
    "Cross-functional / All Departments",
    "Others"
  ]
}""")
