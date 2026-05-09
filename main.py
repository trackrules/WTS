#!/usr/bin/env python
# coding: utf-8

import math, datetime, sqlite3
from pathlib import Path
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from statistics import mean

st.set_page_config(page_title='TS Modelling Tool', page_icon=":bike:", layout="wide")


st.header("Modelling Tool")
update = datetime.date.today() + pd.DateOffset(hour=12)

RIDER_DB = Path(__file__).with_name("riders.db")
RIDER_FIELDS = [
    "seat_max_rpm",
    "seat_max_torque",
    "seat_cda",
    "stand_max_rpm",
    "stand_max_torque",
    "stand_cda",
    "total_mass",
    "sprocket",
    "chainring",
    "seat_height",
]
DEFAULT_RIDERS = {
    "Petch": [235, 207, 0.2050, 240, 223, 0.2563, 71.9, 15, 54, 0.96],
    "Shaane": [233, 253, 0.2340, 227, 289, 0.2925, 91.8, 15, 62, 1.04],
    "Ellesse": [238, 202, 0.2180, 217, 270, 0.2725, 86.9, 15, 63, 1.01],
}


def rider_db_connection():
    return sqlite3.connect(RIDER_DB)


def init_rider_db():
    with rider_db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS riders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                seat_max_rpm REAL NOT NULL,
                seat_max_torque REAL NOT NULL,
                seat_cda REAL NOT NULL,
                stand_max_rpm REAL NOT NULL,
                stand_max_torque REAL NOT NULL,
                stand_cda REAL NOT NULL,
                total_mass REAL NOT NULL,
                sprocket INTEGER NOT NULL,
                chainring INTEGER NOT NULL,
                seat_height REAL NOT NULL
            )
            """
        )
        for name, specs in DEFAULT_RIDERS.items():
            conn.execute(
                f"""
                INSERT OR IGNORE INTO riders (name, {", ".join(RIDER_FIELDS)})
                VALUES ({", ".join(["?"] * (len(RIDER_FIELDS) + 1))})
                """,
                [name, *specs],
            )


def load_riders():
    with rider_db_connection() as conn:
        rows = conn.execute(
            f"SELECT id, name, {', '.join(RIDER_FIELDS)} FROM riders ORDER BY name"
        ).fetchall()
    return [
        {
            "id": row[0],
            "name": row[1],
            "specs": list(row[2:]),
        }
        for row in rows
    ]


def add_rider(name, specs):
    with rider_db_connection() as conn:
        conn.execute(
            f"""
            INSERT INTO riders (name, {", ".join(RIDER_FIELDS)})
            VALUES ({", ".join(["?"] * (len(RIDER_FIELDS) + 1))})
            """,
            [name, *specs],
        )


def update_rider(rider_id, specs):
    assignments = ", ".join(f"{field} = ?" for field in RIDER_FIELDS)
    with rider_db_connection() as conn:
        conn.execute(
            f"UPDATE riders SET {assignments} WHERE id = ?",
            [*specs, rider_id],
        )


def intp(xval, df, xcol, ycol):
    return np.interp([xval], df[xcol], df[ycol])

calcs = ["Female Team Sprint"]
Calc = st.selectbox("Select Model:", calcs, key="Calc_selector")

if Calc == "Female Team Sprint":
    init_rider_db()
    riders = load_riders()
    rider_lookup = {rider["id"]: rider for rider in riders}

    st.subheader("Team order")
    if len(riders) < 3:
        st.error("Add at least three riders before running the team sprint model.")
        st.stop()

    rider_ids = [rider["id"] for rider in riders]
    default_ids = [
        next((rider["id"] for rider in riders if rider["name"] == name), rider_ids[0])
        for name in ("Petch", "Shaane", "Ellesse")
    ]

    def rider_label(rider_id):
        return rider_lookup[rider_id]["name"]

    def selected_rider(container, label, options, default_id, key):
        current_id = st.session_state.get(key, default_id)
        if current_id not in options:
            current_id = default_id if default_id in options else options[0]
            st.session_state[key] = current_id
        return container.selectbox(label, options, index=options.index(current_id), format_func=rider_label, key=key)

    c1, c2, c3 = st.columns(3)
    rider_1_id = selected_rider(c1, "Rider 1:", rider_ids, default_ids[0], "rider_1_selector")
    rider_2_options = [rider_id for rider_id in rider_ids if rider_id != rider_1_id]
    rider_2_default = default_ids[1] if default_ids[1] in rider_2_options else rider_2_options[0]
    rider_2_id = selected_rider(c2, "Rider 2:", rider_2_options, rider_2_default, "rider_2_selector")
    rider_3_options = [rider_id for rider_id in rider_ids if rider_id not in (rider_1_id, rider_2_id)]
    rider_3_default = default_ids[2] if default_ids[2] in rider_3_options else rider_3_options[0]
    rider_3_id = selected_rider(c3, "Rider 3:", rider_3_options, rider_3_default, "rider_3_selector")

    selected_riders = [rider_lookup[rider_id] for rider_id in (rider_1_id, rider_2_id, rider_3_id)]
    rider_names = [rider["name"] for rider in selected_riders]
    rider_defaults = [rider["specs"] for rider in selected_riders]

    def rider_inputs(name, kn, d):
        st.subheader(f"{name} specs")
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        v = [
            c1.number_input("Seated Max RPM:",    min_value=0.01, max_value=500.0,  value=float(d[0]), key=f"{kn}_1"),
            c2.number_input("Seated Max Torque:", min_value=0.01, max_value=500.0,  value=float(d[1]), key=f"{kn}_2"),
            c3.number_input("Seated CdA:",        min_value=0.0001, max_value=2.0,  value=float(d[2]), step=1e-4, format="%.4f", key=f"{kn}_3"),
            c4.number_input("Standing Max RPM:",  min_value=0.01, max_value=500.0,  value=float(d[3]), key=f"{kn}_4"),
            c5.number_input("Standing Max Torque:", min_value=0.01, max_value=500.0, value=float(d[4]), key=f"{kn}_5"),
            c6.number_input("Standing CdA:",      min_value=0.0,  max_value=20.0,   value=float(d[5]), step=1e-4, format="%.4f", key=f"{kn}_6"),
        ]
        c1, c2, c3, c4 = st.columns(4)
        v += [
            c1.number_input("Total Mass:",  min_value=40.0, max_value=150.0, value=float(d[6]), step=0.1, format="%.1f", key=f"{kn}_7"),
            c2.number_input("Sprocket:",    min_value=12,   max_value=22,    value=int(d[7]),   step=1,   key=f"{kn}_8"),
            c3.number_input("Chain Ring:",  min_value=40,   max_value=100,   value=int(d[8]),   step=1,   key=f"{kn}_9"),
            c4.number_input("Seat Height:", min_value=0.50, max_value=2.00,  value=float(d[9]),            key=f"{kn}_10"),
        ]
        return v

    with st.expander("New Rider"):
        with st.form("new_rider_form", clear_on_submit=True):
            new_name = st.text_input("Rider Name:", key="new_rider_name")
            new_specs = rider_inputs("New Rider", "new_rider", DEFAULT_RIDERS["Petch"])
            add_new_rider = st.form_submit_button("Add Rider")
            if add_new_rider:
                clean_name = new_name.strip()
                if not clean_name:
                    st.error("Enter a rider name before adding.")
                else:
                    try:
                        add_rider(clean_name, new_specs)
                        st.success(f"Added {clean_name} to the rider database.")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error(f"A rider named {clean_name} already exists.")

    with st.sidebar:
        st.subheader("Global specs")
        air_density           = st.number_input("Air Density:",             min_value=0.001, max_value=3.2,   value=1.168, step=1e-3, format="%.3f", key="4_1")
        dist_at_sit           = st.number_input("Distance at sit:",         min_value=0.01,  max_value=750.0, value=150.0, step=0.1,  format="%.1f", key="4_2")
        standing_fatigue_rate = st.number_input("Standing Fatigue Rate (%):",min_value=0.01, max_value=99.99, value=1.0,   step=1e-2, format="%.2f", key="4_3")
        seated_fatigue_rate   = st.number_input("Seated Fatigue Rate (%):", min_value=0.01,  max_value=99.99, value=1.0,   step=1e-2, format="%.2f", key="4_4")
        fatigue_onset         = st.number_input("Onset of Fatigue (s):",    min_value=0.1,   max_value=2.0,   value=1.0,   step=0.1,  format="%.1f", key="4_5")
        track_circumference   = st.selectbox("Track Circumference:",        [250, 333, 500],                              key="Track_circumference")
        straight_bank_angle   = st.number_input("Straight Bank Angle:",     min_value=0.0, max_value=90.0, value=13.00)
        bend_bank_angle       = st.number_input("Bend Bank Angle:",         min_value=0.0, max_value=90.0, value=46.13)
        pl_to_trans           = st.number_input("Distance from Pursuit Line to Transition:", min_value=0.0, max_value=90.0, value=31.25)
        transition_length     = st.number_input("Transition length:",       min_value=0.0, max_value=90.0, value=10.00)

    with st.form("my_form"):
        r1 = rider_inputs(rider_names[0], f"1_{rider_1_id}", rider_defaults[0])
        r2 = rider_inputs(rider_names[1], f"2_{rider_2_id}", rider_defaults[1])
        r3 = rider_inputs(rider_names[2], f"3_{rider_3_id}", rider_defaults[2])
        submitted = st.form_submit_button("Update Specs")
        if submitted:
            update_rider(rider_1_id, r1)
            update_rider(rider_2_id, r2)
            update_rider(rider_3_id, r3)
            st.success("Updated selected rider specs in the database.")

    (seat_max_RPM_1, seat_max_torque_1, seat_CdA_1, stand_max_RPM_1, stand_max_torque_1, stand_CdA_1, total_mass_1, sprocket_1, chainring_1, seat_height_1) = r1
    (seat_max_RPM_2, seat_max_torque_2, seat_CdA_2, stand_max_RPM_2, stand_max_torque_2, stand_CdA_2, total_mass_2, sprocket_2, chainring_2, seat_height_2) = r2
    (seat_max_RPM_3, seat_max_torque_3, seat_CdA_3, stand_max_RPM_3, stand_max_torque_3, stand_CdA_3, total_mass_3, sprocket_3, chainring_3, seat_height_3) = r3

    # --- Constants ---
    wheel_circ, bike_length = 2.096, 1.7122
    ks, mu_rr, lean_smoothing, increment, efficiency = 0.0072, 0.0016, 1, 0.1, 0.97
    rad_of_curve = (250 - 4 * pl_to_trans) / (2 * math.pi)
    deg_to_rad, rad_to_deg = math.pi / 180, 180 / math.pi

    # --- Athlete class ---
    class Athlete:
        def __init__(self, seat_max_RPM, seat_max_torque, stand_max_RPM, stand_max_torque,
                     stand_CdA, seat_CdA, total_mass, gear, seat_height, max_power,
                     stand_TC_slope, seat_TC_slope):
            self.seat_max_RPM = seat_max_RPM; self.seat_max_torque = seat_max_torque
            self.stand_max_RPM = stand_max_RPM; self.stand_max_torque = stand_max_torque
            self.stand_CdA = stand_CdA; self.seat_CdA = seat_CdA
            self.total_mass = total_mass; self.gear = gear
            self.seat_height = seat_height; self.max_power = max_power
            self.stand_TC_slope = stand_TC_slope; self.seat_TC_slope = seat_TC_slope

        def initialize_state(self, initial_speed, bank_angle, rad_of_curve, air_density, mu_rr, ks, efficiency, bike_length):
            self.time = 0; self.COM_speed = initial_speed; self.COM_dist = 0
            self.CdA = self.stand_CdA; self.cadence = 0; self.torque = self.stand_max_torque
            self.power_input = self.cadence * self.torque * (math.pi / 30)
            self.power_usable = self.power_input * efficiency; self.acc_fatigue = 0
            self.bank = bank_angle; self.lean = 0
            self.camber = abs(self.bank - self.lean)
            self.r_wh = 2 * rad_of_curve; self.r_cm = 2 * rad_of_curve
            self.prop_force = 2 * math.pi * self.torque / (2.096 * (self.gear / 27))
            self.aero_drag = 0.5 * air_density * self.CdA * self.COM_speed ** 2
            self.weight_force = 9.81 * self.total_mass; self.centripetal_force = 0
            self.reaction_force = math.sqrt(self.weight_force ** 2 + self.centripetal_force ** 2)
            self.normal_force = self.reaction_force * math.cos(math.radians(self.camber))
            self.rr = self.normal_force * mu_rr * (1 + (self.camber * ks))
            self.wheel_speed = 0; self.wheel_dist = 0
            self.segment = self.wheel_dist % 125
            self.accel = (self.prop_force - (self.rr + self.aero_drag)) / self.total_mass
            self.air_speed = 0; self.gap = -bike_length

    def make_athlete(rpm_s, tor_s, rpm_st, tor_st, cda_st, cda_s, mass, chain, spr, sh):
        return Athlete(rpm_s, tor_s, rpm_st, tor_st, cda_st, cda_s, mass,
                       27 * chain / spr, sh, rpm_s * tor_s * math.pi / 120,
                       -tor_st / rpm_st, -tor_s / rpm_s)

    p1 = make_athlete(seat_max_RPM_1, seat_max_torque_1, stand_max_RPM_1, stand_max_torque_1, stand_CdA_1, seat_CdA_1, total_mass_1, chainring_1, sprocket_1, seat_height_1)
    p2 = make_athlete(seat_max_RPM_2, seat_max_torque_2, stand_max_RPM_2, stand_max_torque_2, stand_CdA_2, seat_CdA_2, total_mass_2, chainring_2, sprocket_2, seat_height_2)
    p3 = make_athlete(seat_max_RPM_3, seat_max_torque_3, stand_max_RPM_3, stand_max_torque_3, stand_CdA_3, seat_CdA_3, total_mass_3, chainring_3, sprocket_3, seat_height_3)

    for rider, spd in ((p1, 2), (p2, 2), (p3, 1.6)):
        rider.initialize_state(spd, straight_bank_angle, rad_of_curve, air_density, mu_rr, ks, efficiency, bike_length)

    # --- Track geometry ---
    def get_bank_lean_camber(segment, lean_initial, v_com, seat_height):
        bend_length = 125 - 2 * (pl_to_trans + transition_length)
        r_wh = rad_of_curve
        if (segment < pl_to_trans) or (segment > 125 - pl_to_trans):
            bank = straight_bank_angle
            r_wh = r_cm = 100000
        elif segment <= pl_to_trans + transition_length:
            pct = (segment - pl_to_trans) / transition_length
            bank = straight_bank_angle + pct * (bend_bank_angle - straight_bank_angle)
            r_wh = 2 * rad_of_curve - pct * rad_of_curve
        elif segment <= pl_to_trans + transition_length + bend_length:
            bank = bend_bank_angle
        else:
            pct = (segment - (pl_to_trans + transition_length + bend_length)) / transition_length
            bank = bend_bank_angle + pct * (straight_bank_angle - bend_bank_angle)
            r_wh = rad_of_curve + pct * rad_of_curve
        lean = rad_to_deg * math.atan(v_com ** 2 / (9.81 * (r_wh - seat_height * math.sin(deg_to_rad * lean_initial))))
        while lean - lean_initial > 0.1:
            lean_initial = lean
            lean = rad_to_deg * math.atan(v_com ** 2 / (9.81 * (r_wh - seat_height * math.sin(deg_to_rad * lean))))
        r_cm = r_wh - seat_height * math.sin(deg_to_rad * lean) if r_wh < 2 * rad_of_curve else r_wh
        return bank, r_wh, r_cm, lean, bank - lean

    # --- Simulation helpers ---
    _BASE_FIELDS = ('COM_speed', 'COM_dist', 'bank', 'r_wh', 'r_cm', 'lean', 'camber',
                    'wheel_speed', 'wheel_dist', 'cadence', 'torque', 'power_input',
                    'power_usable', 'prop_force', 'aero_drag', 'weight_force', 'segment',
                    'centripetal_force', 'reaction_force', 'normal_force', 'rr', 'accel')

    def new_data(rider, with_demand=False):
        d = {'time': [rider.time]}
        d.update({k: [getattr(rider, k)] for k in _BASE_FIELDS})
        d['gap'] = [getattr(rider, 'gap', 0)]
        d['air_speed'] = [getattr(rider, 'air_speed', 0)]
        if with_demand:
            d.update({k: [getattr(rider, k, 1 if k == 'dem_sup' else 0)]
                      for k in ('accel_demand', 'rr_demand', 'aero_demand', 'power_demand', 'dem_sup')})
        return d

    def append_state(rider, d, with_demand=False):
        d['time'].append(rider.time)
        for k in _BASE_FIELDS:
            d[k].append(getattr(rider, k))
        d['gap'].append(getattr(rider, 'gap', 0))
        d['air_speed'].append(getattr(rider, 'air_speed', 0))
        if with_demand:
            for k in ('accel_demand', 'rr_demand', 'aero_demand', 'power_demand', 'dem_sup'):
                d[k].append(getattr(rider, k))

    def update_lean(rider, leans):
        rider.bank, rider.r_wh, rider.r_cm, rider.lean, rider.camber = \
            get_bank_lean_camber(rider.segment, rider.lean, rider.COM_speed, rider.seat_height)
        leans.append(rider.lean)
        if len(leans) > lean_smoothing:
            leans[:] = leans[1:]
        rider.lean = mean(leans)

    def update_kinematics(rider):
        rider.wheel_speed = rider.COM_speed * (rider.r_wh / rider.r_cm)
        rider.wheel_dist += rider.wheel_speed * increment
        rider.cadence = 60 * rider.wheel_speed / ((rider.gear / 27) * wheel_circ)

    def update_forces(rider, cda):
        rider.power_input = rider.cadence * rider.torque * (math.pi / 30)
        rider.power_usable = rider.power_input * efficiency
        rider.prop_force = 2 * math.pi * efficiency * rider.torque / (2.096 * (rider.gear / 27))
        rider.aero_drag = 0.5 * air_density * cda * rider.COM_speed ** 2
        rider.weight_force = 9.81 * rider.total_mass
        rider.segment = rider.wheel_dist % 125
        rider.centripetal_force = (
            0 if (rider.segment < pl_to_trans or rider.segment > 125 - pl_to_trans)
            else (rider.total_mass * rider.COM_speed ** 2) / rider.r_cm
        )
        rider.reaction_force = math.sqrt(rider.weight_force ** 2 + rider.centripetal_force ** 2)
        rider.normal_force = rider.reaction_force * math.cos(deg_to_rad * rider.camber)
        rider.rr = rider.normal_force * mu_rr * (1 + abs(rider.camber) * ks)
        rider.accel = (rider.prop_force - (rider.rr + rider.aero_drag)) / rider.total_mass

    def make_df(d, extra_cols=()):
        cols = ['time'] + list(_BASE_FIELDS) + ['gap', 'air_speed'] + list(extra_cols)
        return pd.DataFrame({c: d[c] for c in cols}).rename(columns={'time': 'Time'})

    # --- P1 simulation ---
    p1d = new_data(p1)
    p1_leans = []
    for is_standing, stop_dist in [(True, dist_at_sit), (False, 250)]:
        if not is_standing:
            p1.CdA = p1.seat_CdA
        while p1.wheel_dist < stop_dist:
            p1.time += increment
            p1.COM_speed += increment * p1.accel
            p1.COM_dist += p1.COM_speed * increment
            update_lean(p1, p1_leans)
            update_kinematics(p1)
            if is_standing:
                if p1.time < fatigue_onset:
                    p1.torque = p1.stand_max_torque + p1.stand_TC_slope * p1.cadence
                else:
                    p1.acc_fatigue += increment * standing_fatigue_rate / 100
                    p1.torque = p1.stand_max_torque * (1 - p1.acc_fatigue) + p1.stand_TC_slope * p1.cadence
                update_forces(p1, p1.stand_CdA)
            else:
                p1.acc_fatigue += increment * seated_fatigue_rate / 100
                p1.torque = p1.seat_max_torque * (1 - p1.acc_fatigue) + p1.seat_TC_slope * p1.cadence
                update_forces(p1, p1.seat_CdA)
            append_state(p1, p1d)
    df_p1 = make_df(p1d)

    # --- P2 simulation ---
    p2d = new_data(p2)
    p2_leans = []
    count = 0
    for is_standing, stop_dist in [(True, dist_at_sit), (False, 500)]:
        if not is_standing:
            p2.CdA = p2.seat_CdA
        while p2.wheel_dist < stop_dist:
            p2.time += increment
            p2.COM_speed += increment * p2.accel
            p2.COM_dist += p2.COM_speed * increment
            update_lean(p2, p2_leans)
            update_kinematics(p2)
            p2.gap = df_p1["wheel_dist"][count] - p2.wheel_dist - bike_length if count < len(df_p1) else 0
            p2.air_speed = p2.COM_speed
            cda = p2.stand_CdA if is_standing else p2.seat_CdA
            if is_standing:
                if p2.time < fatigue_onset:
                    p2.torque = p2.stand_max_torque + p2.stand_TC_slope * p2.cadence
                else:
                    p2.acc_fatigue += increment * standing_fatigue_rate / 100
                    p2.torque = p2.stand_max_torque * (1 - p2.acc_fatigue) + p2.stand_TC_slope * p2.cadence
            else:
                p2.acc_fatigue += increment * seated_fatigue_rate / 100
                p2.torque = p2.seat_max_torque * (1 - p2.acc_fatigue) + p2.seat_TC_slope * p2.cadence
            update_forces(p2, cda)
            if p2.gap > 0.2:
                p2.aero_drag *= (100 - (-8.1136 * p2.gap + 50.051)) / 100
                p2.accel = (p2.prop_force - (p2.rr + p2.aero_drag)) / p2.total_mass
            count += 1
            append_state(p2, p2d)
    df_p2 = make_df(p2d)

    # --- P3 simulation ---
    p3.dem_sup = 1; p3.accel_demand = 0; p3.rr_demand = 0; p3.aero_demand = 0; p3.power_demand = 0
    p3d = new_data(p3, with_demand=True)
    p3_leans = []
    count = 1
    for is_standing, stop_dist in [(True, dist_at_sit), (False, 750)]:
        if not is_standing:
            p3.CdA = p3.seat_CdA
        while p3.wheel_dist < stop_dist:
            if count < len(df_p2):
                p3.accel_demand = p3.total_mass * df_p2["accel"][count] * df_p2["wheel_speed"][count]
                p3.rr_demand = p3.rr * df_p2["wheel_speed"][count]
                p3.aero_demand = 0.5 * air_density * p3.CdA * p3.COM_speed * p3.air_speed ** 2
                p3.power_demand = p3.accel_demand + p3.rr_demand + p3.aero_demand
            else:
                p3.accel_demand = p3.rr_demand = p3.aero_demand = p3.power_demand = 0
            p3.time += increment
            p3.COM_speed += increment * p3.accel
            p3.COM_dist += p3.COM_speed * increment
            update_lean(p3, p3_leans)
            update_kinematics(p3)
            p3.gap = df_p2["wheel_dist"][count] - p3.wheel_dist - bike_length if count < len(df_p2) else 0
            p3.air_speed = p3.COM_speed
            cda = p3.stand_CdA if is_standing else p3.seat_CdA
            if is_standing:
                if p3.time < fatigue_onset:
                    p3.torque = p3.stand_max_torque + p3.stand_TC_slope * p3.cadence
                else:
                    p3.acc_fatigue += increment * p3.dem_sup * standing_fatigue_rate / 100
                    p3.torque = p3.stand_max_torque * (1 - p3.acc_fatigue) + p3.stand_TC_slope * p3.cadence
            else:
                p3.acc_fatigue += increment * p3.dem_sup * seated_fatigue_rate / 100
                p3.torque = p3.seat_max_torque * (1 - p3.acc_fatigue) + p3.seat_TC_slope * p3.cadence
            update_forces(p3, cda)
            p3.dem_sup = p3.power_demand / p3.power_usable if p3.power_usable > p3.power_demand else 1
            if p3.gap > 0.2:
                p3.aero_drag *= (100 - (-8.1136 * p3.gap + 50.051)) / 100
                p3.accel = (p3.prop_force - (p3.rr + p3.aero_drag)) / p3.total_mass
            count += 1
            append_state(p3, p3d, with_demand=True)
    df_p3 = make_df(p3d, extra_cols=('accel_demand', 'rr_demand', 'aero_demand', 'power_demand', 'dem_sup'))

    fig_dem_v_supp = px.line(df_p3, x="Time", y=[df_p3["dem_sup"], df_p3["COM_speed"], df_p3["gap"]])
    # st.plotly_chart(fig_dem_v_supp, use_container_width=True)

    # --- Summary ---
    st.header("Summary")
    dists_p1 = [62.5, 125, 187.5, 250]
    dists_p2 = dists_p1 + [312.5, 375, 437.5, 500]
    dists_p3 = dists_p2 + [562.5, 625, 687.5, 750]

    def qt(d, df_px):
        return round(intp(d, df_px, 'wheel_dist', 'Time')[0], 3)

    p1_qt = {d: qt(d, df_p1) for d in dists_p1}
    p2_qt = {d: qt(d, df_p2) for d in dists_p2}
    p3_qt = {d: qt(d, df_p3) for d in dists_p3}

    df_time = pd.DataFrame([1, 2, 3], columns=["Time"])
    for d in dists_p1:
        df_time[str(d)] = [p1_qt[d], p2_qt[d], p3_qt[d]]
    for d in [312.5, 375, 437.5, 500]:
        df_time[str(d)] = [0, p2_qt[d], p3_qt[d]]
    for d in [562.5, 625, 687.5, 750]:
        df_time[str(d)] = [0, 0, p3_qt[d]]
    st.dataframe(df_time, use_container_width=False)

    df_gap = pd.DataFrame([2, 3], columns=["Time_gap"])
    for d in dists_p1:
        df_gap[str(d)] = [p2_qt[d] - p1_qt[d], p3_qt[d] - p2_qt[d]]
    for d in [312.5, 375, 437.5, 500]:
        df_gap[str(d)] = [0, p3_qt[d] - p2_qt[d]]
    st.dataframe(df_gap, use_container_width=False)

    df_dist_gap = pd.DataFrame([2, 3], columns=["Dist_gap"])
    for d in dists_p1:
        df_dist_gap[str(d)] = [round(intp(p1_qt[d], df_p2, 'Time', 'gap')[0], 2),
                               round(intp(p2_qt[d], df_p3, 'Time', 'gap')[0], 2)]
    for d in [312.5, 375, 437.5, 500]:
        df_dist_gap[str(d)] = [0, round(intp(p2_qt[d], df_p3, 'Time', 'gap')[0], 2)]
    st.dataframe(df_dist_gap, use_container_width=False)

    def make_summary_df(field, label):
        df_s = pd.DataFrame([1, 2, 3], columns=[label])
        for d in dists_p1:
            df_s[str(d)] = [round(intp(p1_qt[d], df_p1, 'Time', field)[0], 2),
                            round(intp(p2_qt[d], df_p2, 'Time', field)[0], 2),
                            round(intp(p3_qt[d], df_p3, 'Time', field)[0], 2)]
        for d in [312.5, 375, 437.5, 500]:
            df_s[str(d)] = [0,
                            round(intp(p2_qt[d], df_p2, 'Time', field)[0], 2),
                            round(intp(p3_qt[d], df_p3, 'Time', field)[0], 2)]
        for d in [562.5, 625, 687.5, 750]:
            df_s[str(d)] = [0, 0, round(intp(p3_qt[d], df_p3, 'Time', field)[0], 2)]
        return df_s

    df_cadence = make_summary_df('cadence', 'Cadence')
    st.dataframe(df_cadence, use_container_width=False)

    df_wheel_speed = make_summary_df('wheel_speed', 'wheel_speed')
    df_wheel_speed = df_wheel_speed.apply(lambda x: x * 3.6)
    df_wheel_speed["wheel_speed"] = [1, 2, 3]
    st.write("Wheel speed in km/h")
    st.dataframe(df_wheel_speed, use_container_width=False)

    # --- Per-rider output ---
    def power_speed_fig(df_px, label):
        fig = go.Figure()
        fig.add_trace(go.Scatter(mode='lines', x=df_px["Time"], y=df_px["power_usable"], name=f"{label} Power", yaxis='y'))
        fig.add_trace(go.Scatter(mode='lines', x=df_px["Time"], y=df_px["wheel_speed"], name=f"{label} Wheel speed", yaxis="y2"))
        fig.update_layout(
            xaxis=dict(domain=[0.0, 1.0]),
            yaxis=dict(title="Power (W)"),
            yaxis2=dict(title="Wheel speed", overlaying="y", side="right", position=1.0),
            title_text="Power and Wheel speed"
        )
        return fig

    def time_to(dist, df_px):
        row = df_px.iloc[(df_px['wheel_dist'] - dist).abs().argsort()[:2]].reset_index(drop=True)
        return row["Time"][1] + (dist - row["wheel_dist"][1]) / row["wheel_speed"][1]

    st.header("P1 numbers")
    df_p1
    p1_250_time = df_p1["Time"][len(df_p1) - 2] + ((250 - df_p1["wheel_dist"][len(df_p1) - 2]) / df_p1["wheel_speed"][len(df_p1) - 2])
    st.write(f"Time to 250m is {round(p1_250_time, 3)}")
    # st.plotly_chart(px.line(df_p1, x="Time", y="lean"), use_container_width=True)
    st.plotly_chart(power_speed_fig(df_p1, "P1"), width='stretch')

    st.header("P2 numbers")
    df_p2
    st.write(f"Time to 250m is {round(time_to(250, df_p2), 3)}")
    st.write(f"Time to 500m is {round(time_to(500, df_p2), 3)}")
    st.plotly_chart(power_speed_fig(df_p2, "p2"), width='stretch')

    st.header("P3 numbers")
    df_p3
    st.write(f"Time to 250m is {round(time_to(250, df_p3), 3)}")
    st.write(f"Time to 500m is {round(time_to(500, df_p3), 3)}")
    st.write(f"Time to 750m is {round(time_to(750, df_p3), 3)}")

    fig_all = go.Figure()
    for df_px, label in [(df_p1, "p1"), (df_p2, "p2"), (df_p3, "p3")]:
        fig_all.add_trace(go.Scatter(mode='lines', x=df_px["Time"], y=df_px["power_usable"], name=f"{label} Power", yaxis='y'))
        fig_all.add_trace(go.Scatter(mode='lines', x=df_px["Time"], y=df_px["wheel_speed"], name=f"{label} Wheel speed", yaxis="y2"))
    fig_all.update_layout(
        xaxis=dict(domain=[0.0, 1.0]),
        yaxis=dict(title="Power (W)"),
        yaxis2=dict(title="Wheel speed", overlaying="y", side="right", position=1.0),
        title_text="Power and Wheel speed"
    )
    st.plotly_chart(fig_all, width='stretch')
