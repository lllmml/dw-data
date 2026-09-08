"""Versioned filename and exact header registry for Nanjing CSV intake."""

from dataclasses import dataclass
from enum import StrEnum


class SourceFileType(StrEnum):
    STATION = "STATION"
    BUS = "BUS"
    SWITCH = "SWITCH"
    DISCONNECTOR = "DISCONNECTOR"
    FEEDER = "FEEDER"
    EARTHING_SWITCH = "EARTHING_SWITCH"
    ACCESS_POINT = "ACCESS_POINT"
    LINE = "LINE"
    TRANSFORMER = "TRANSFORMER"
    LOAD = "LOAD"
    DER = "DER"
    SIM_CONFIG = "SIM_CONFIG"


@dataclass(frozen=True, slots=True)
class SourceFileSchema:
    file_type: SourceFileType
    filename: str
    header: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SourceSchemaRegistry:
    mapping_id: str
    mapping_version: str
    files: tuple[SourceFileSchema, ...]

    def __post_init__(self) -> None:
        if not self.mapping_id or not self.mapping_version:
            raise ValueError("mapping identity and version must be non-empty")
        if len({schema.filename for schema in self.files}) != len(self.files):
            raise ValueError("source schema filenames must be unique")
        if len({schema.file_type for schema in self.files}) != len(self.files):
            raise ValueError("source file types must be unique")

    def for_filename(self, filename: str) -> SourceFileSchema | None:
        return next(
            (schema for schema in self.files if schema.filename == filename), None
        )

    def for_type(self, file_type: SourceFileType) -> SourceFileSchema:
        for schema in self.files:
            if schema.file_type is file_type:
                return schema
        raise KeyError(file_type)


NANJING_SOURCE_SCHEMA = SourceSchemaRegistry(
    mapping_id="nanjing_csv",
    mapping_version="0.2.0",
    files=(
        SourceFileSchema(
            SourceFileType.STATION,
            "01_Station.csv",
            (
                "Station_ID",
                "Station_Type",
                "Station_Name",
                "Station_Voltage_Level",
                "Station_Lon",
                "Station_Lat",
            ),
        ),
        SourceFileSchema(
            SourceFileType.BUS,
            "02_Bus.csv",
            (
                "Bus_ID",
                "Bus_Name",
                "Bus_BaseKV",
                "Bus_Phase",
                "Bus_Station_ID",
                "Bus_IsSource",
            ),
        ),
        SourceFileSchema(
            SourceFileType.SWITCH,
            "03_Switch.csv",
            (
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
        ),
        SourceFileSchema(
            SourceFileType.DISCONNECTOR,
            "04_Disconnector.csv",
            (
                "Disconnector_ID",
                "Disconnector_FromBus",
                "Disconnector_ToBus",
                "Disconnector_NormalState",
            ),
        ),
        SourceFileSchema(
            SourceFileType.FEEDER,
            "05_Feeder.csv",
            ("Feeder_ID", "Feeder_Name", "Feeder_SourceBus"),
        ),
        SourceFileSchema(
            SourceFileType.EARTHING_SWITCH,
            "06_EarthingSwitch.csv",
            (
                "EarthingSwitch_ID",
                "EarthingSwitch_Bus",
                "EarthingSwitch_State",
            ),
        ),
        SourceFileSchema(
            SourceFileType.ACCESS_POINT,
            "07_AccessPoint.csv",
            (
                "AccessPoint_ID",
                "AccessPoint_Bus",
                "AccessPoint_Phase",
                "AccessPoint_UserType",
                "AccessPoint_ContractCapacity_kVA",
            ),
        ),
        SourceFileSchema(
            SourceFileType.LINE,
            "08_Line.csv",
            (
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
        ),
        SourceFileSchema(
            SourceFileType.TRANSFORMER,
            "09_Transformer.csv",
            (
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
        ),
        SourceFileSchema(
            SourceFileType.LOAD,
            "10_Load.csv",
            (
                "Load_ID",
                "Load_Bus",
                "Load_Phase",
                "Load_P_kW",
                "Load_Q_kVAR",
                "Load_PF",
            ),
        ),
        SourceFileSchema(
            SourceFileType.DER,
            "11_DER.csv",
            (
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
        ),
        SourceFileSchema(
            SourceFileType.SIM_CONFIG,
            "12_SimConfig.csv",
            ("Config_Key", "Config_Value"),
        ),
    ),
)
