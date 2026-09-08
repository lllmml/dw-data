from grid_case_generator.io.nanjing_source.schema import (
    NANJING_SOURCE_SCHEMA,
    SourceFileType,
)


EXPECTED_HEADERS = {
    "01_Station.csv": (
        "Station_ID",
        "Station_Type",
        "Station_Name",
        "Station_Voltage_Level",
        "Station_Lon",
        "Station_Lat",
    ),
    "02_Bus.csv": (
        "Bus_ID",
        "Bus_Name",
        "Bus_BaseKV",
        "Bus_Phase",
        "Bus_Station_ID",
        "Bus_IsSource",
    ),
    "03_Switch.csv": (
        "Switch_ID",
        "Switch_FromBus",
        "Switch_ToBus",
        "Switch_Phase",
        "Switch_NormalState",
        "Switch_IsTie",
        "Switch_RatedCurrent_A",
        "Switch_HasMeasurement",
        "Switch_Meas_I_A",
        "Switch_Meas_P_kW",
        "Switch_Meas_Q_kVAR",
        "Switch_Meas_Timestamp",
    ),
    "04_Disconnector.csv": (
        "Disconnector_ID",
        "Disconnector_FromBus",
        "Disconnector_ToBus",
        "Disconnector_NormalState",
    ),
    "05_Feeder.csv": ("Feeder_ID", "Feeder_Name", "Feeder_SourceBus"),
    "06_EarthingSwitch.csv": (
        "EarthingSwitch_ID",
        "EarthingSwitch_Bus",
        "EarthingSwitch_State",
    ),
    "07_AccessPoint.csv": (
        "AccessPoint_ID",
        "AccessPoint_Bus",
        "AccessPoint_Phase",
        "AccessPoint_UserType",
        "AccessPoint_ContractCapacity_kVA",
    ),
    "08_Line.csv": (
        "Line_ID",
        "Line_FromBus",
        "Line_ToBus",
        "Line_Phase",
        "Line_Type",
        "Line_Model",
        "Line_Length_km",
        "Line_R1_ohm_per_km",
        "Line_X1_ohm_per_km",
        "Line_NumCircuits",
    ),
    "09_Transformer.csv": (
        "Transformer_ID",
        "Transformer_FromBus",
        "Transformer_ToBus",
        "Transformer_Phase",
        "Transformer_RatedCapacity_kVA",
        "Transformer_HighVoltage_kV",
        "Transformer_LowVoltage_kV",
        "Transformer_R_pct",
        "Transformer_X_pct",
        "Transformer_ConnHV",
        "Transformer_ConnLV",
        "Transformer_NumTaps",
        "Transformer_TapRange",
    ),
    "10_Load.csv": (
        "Load_ID",
        "Load_Bus",
        "Load_Phase",
        "Load_P_kW",
        "Load_Q_kVAR",
        "Load_PF",
    ),
    "11_DER.csv": (
        "DER_ID",
        "DER_Bus",
        "DER_Phase",
        "DER_Type",
        "DER_RatedCapacity_kVA",
        "DER_RatedPower_kW",
        "DER_PF",
        "DER_ConnType",
        "DER_ControlMode",
    ),
    "12_SimConfig.csv": ("Config_Key", "Config_Value"),
}


def test_schema_registry_is_versioned_and_exact() -> None:
    assert NANJING_SOURCE_SCHEMA.mapping_id == "nanjing_csv"
    assert NANJING_SOURCE_SCHEMA.mapping_version == "0.2.0"
    assert len(NANJING_SOURCE_SCHEMA.files) == 12
    assert {
        file_schema.filename: file_schema.header
        for file_schema in NANJING_SOURCE_SCHEMA.files
    } == EXPECTED_HEADERS
    assert {schema.file_type for schema in NANJING_SOURCE_SCHEMA.files} == set(
        SourceFileType
    )


def test_registry_lookups_do_not_infer_or_fuzzy_match_names() -> None:
    station = NANJING_SOURCE_SCHEMA.for_type(SourceFileType.STATION)

    assert NANJING_SOURCE_SCHEMA.for_filename("01_Station.csv") is station
    assert NANJING_SOURCE_SCHEMA.for_filename("01_station.csv") is None
    assert NANJING_SOURCE_SCHEMA.for_filename("prefix/01_Station.csv") is None
