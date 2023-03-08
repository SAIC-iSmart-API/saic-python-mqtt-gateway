from saicapi.common_model import ApplicationData, Asn1Type


class OtaChrgMangDataResp(ApplicationData):
    def __init__(self):
        super().__init__('OTAChrgMangDataResp')
        self.bmsReserCtrlDspCmd = None  # INTEGER(0..255),
        self.bmsReserStHourDspCmd = None  # INTEGER(0..255),
        self.bmsReserStMintueDspCmd = None  # INTEGER(0..255),
        self.bmsReserSpHourDspCmd = None  # INTEGER(0..255),
        self.bmsReserSpMintueDspCmd = None  # INTEGER(0..255),
        self.bmsOnBdChrgTrgtSOCDspCmd = None  # INTEGER(0..255),
        self.bms_estd_elec_rng = None  # INTEGER(0..65535),
        self.bmsAltngChrgCrntDspCmd = None  # INTEGER(0..255),
        self.bmsChrgCtrlDspCmd = None  # INTEGER(0..255),
        self.chrgngRmnngTime = None  # INTEGER(0..65535),
        self.chrgngRmnngTimeV = None  # INTEGER(0..255),
        self.bmsChrgOtptCrntReq = None  # INTEGER(0..65535),
        self.bmsChrgOtptCrntReqV = None  # INTEGER(0..255) OPTIONAL,
        self.bmsPackCrnt = None  # INTEGER(0..65535),
        self.bmsPackCrntV = None  # INTEGER(0..255) OPTIONAL,
        self.bmsPackVol = None  # INTEGER(0..65535),
        self.bmsPackSOCDsp = None  # INTEGER(0..65535),
        self.bmsChrgSts = None  # INTEGER(0..255),
        self.bmsChrgSpRsn = None  # INTEGER(0..255),
        self.clstrElecRngToEPT = None  # INTEGER(0..65535),
        self.bmsPTCHeatReqDspCmd = None  # INTEGER(0..255),
        self.bmsPTCHeatResp = None  # INTEGER(0..255) OPTIONAL,
        self.ccuEleccLckCtrlDspCmd = None  # INTEGER(0..255) OPTIONAL,
        self.bmsPTCHeatSpRsn = None  # INTEGER(0..255) OPTIONAL,
        self.bmsDsChrgSpRsn = None  # INTEGER(0..255) OPTIONAL,
        self.disChrgngRmnngTime = None  # INTEGER(0..65535) OPTIONAL,
        self.disChrgngRmnngTimeV = None  # INTEGER(0..255) OPTIONAL,
        self.imcuVehElecRng = None  # INTEGER(0..65535) OPTIONAL,
        self.imcuVehElecRngV = None  # INTEGER(0..255) OPTIONAL,
        self.imcuChrgngEstdElecRng = None  # INTEGER(0..65535) OPTIONAL,
        self.imcuChrgngEstdElecRngV = None  # INTEGER(0..255) OPTIONAL,
        self.imcuDschrgngEstdElecRng = None  # INTEGER(0..65535) OPTIONAL,
        self.imcuDschrgngEstdElecRngV = None  # INTEGER(0..255) OPTIONAL,
        self.chrgngSpdngTime = None  # INTEGER(0..65535) OPTIONAL,
        self.chrgngSpdngTimeV = None  # INTEGER(0..255) OPTIONAL,
        self.chrgngAddedElecRng = None  # INTEGER(0..65535) OPTIONAL,
        self.chrgngAddedElecRngV = None  # INTEGER(0..255) OPTIONAL,
        self.onBdChrgrAltrCrntInptCrnt = None  # INTEGER(0..255) OPTIONAL,
        self.onBdChrgrAltrCrntInptVol = None  # INTEGER(0..255) OPTIONAL,
        self.ccuOnbdChrgrPlugOn = None  # INTEGER(0..255) OPTIONAL,
        self.ccuOffBdChrgrPlugOn = None  # INTEGER(0..255) OPTIONAL,
        self.chrgngDoorPosSts = None  # INTEGER(0..255) OPTIONAL,
        self.chrgngDoorOpenCnd = None  # INTEGER(0..255) OPTIONAL,
        self.chargeStatus = None  # RvsChargingStatus(1),
        self.bmsAdpPubChrgSttnDspCmd = None  # INTEGER(0..255)

    def get_data(self) -> dict:
        data = {
            'bmsReserCtrlDspCmd': self.bmsReserCtrlDspCmd,
            'bmsReserStHourDspCmd': self.bmsReserStHourDspCmd,
            'bmsReserStMintueDspCmd': self.bmsReserStMintueDspCmd,
            'bmsReserSpHourDspCmd': self.bmsReserSpHourDspCmd,
            'bmsReserSpMintueDspCmd': self.bmsReserSpMintueDspCmd,
            'bmsOnBdChrgTrgtSOCDspCmd': self.bmsOnBdChrgTrgtSOCDspCmd,
            'bmsEstdElecRng': self.bms_estd_elec_rng,
            'bmsAltngChrgCrntDspCmd': self.bmsAltngChrgCrntDspCmd,
            'bmsChrgCtrlDspCmd': self.bmsChrgCtrlDspCmd,
            'chrgngRmnngTime': self.chrgngRmnngTime,
            'chrgngRmnngTimeV': self.chrgngRmnngTimeV,
            'bmsChrgOtptCrntReq': self.bmsChrgOtptCrntReq,
            'bmsPackCrnt': self.bmsPackCrnt,
            'bmsPackVol': self.bmsPackVol,
            'bmsPackSOCDsp': self.bmsPackSOCDsp,
            'bmsChrgSts': self.bmsChrgSts,
            'bmsChrgSpRsn': self.bmsChrgSpRsn,
            'clstrElecRngToEPT': self.clstrElecRngToEPT,
            'bmsPTCHeatReqDspCmd': self.bmsPTCHeatReqDspCmd,
            'chargeStatus': self.chargeStatus.get_data(),
            'bmsAdpPubChrgSttnDspCmd': self.bmsAdpPubChrgSttnDspCmd
        }
        self.add_optional_field_to_data(data, 'bmsChrgOtptCrntReqV', self.bmsChrgOtptCrntReqV)
        self.add_optional_field_to_data(data, 'bmsPackCrntV', self.bmsPackCrntV)
        self.add_optional_field_to_data(data, 'bmsPTCHeatResp', self.bmsPTCHeatResp)
        self.add_optional_field_to_data(data, 'ccuEleccLckCtrlDspCmd', self.ccuEleccLckCtrlDspCmd)
        self.add_optional_field_to_data(data, 'bmsPTCHeatSpRsn', self.bmsPTCHeatSpRsn)
        self.add_optional_field_to_data(data, 'bmsDsChrgSpRsn', self.bmsDsChrgSpRsn)
        self.add_optional_field_to_data(data, 'disChrgngRmnngTime', self.disChrgngRmnngTime)
        self.add_optional_field_to_data(data, 'disChrgngRmnngTimeV', self.disChrgngRmnngTimeV)
        self.add_optional_field_to_data(data, 'imcuVehElecRng', self.imcuVehElecRng)
        self.add_optional_field_to_data(data, 'imcuVehElecRngV', self.imcuVehElecRngV)
        self.add_optional_field_to_data(data, 'imcuChrgngEstdElecRng', self.imcuChrgngEstdElecRng)
        self.add_optional_field_to_data(data, 'imcuChrgngEstdElecRngV', self.imcuChrgngEstdElecRngV)
        self.add_optional_field_to_data(data, 'imcuDschrgngEstdElecRng', self.imcuDschrgngEstdElecRng)
        self.add_optional_field_to_data(data, 'imcuDschrgngEstdElecRngV', self.imcuDschrgngEstdElecRngV)
        self.add_optional_field_to_data(data, 'chrgngSpdngTime', self.chrgngSpdngTime)
        self.add_optional_field_to_data(data, 'chrgngSpdngTimeV', self.chrgngSpdngTimeV)
        self.add_optional_field_to_data(data, 'chrgngAddedElecRng', self.chrgngAddedElecRng)
        self.add_optional_field_to_data(data, 'chrgngAddedElecRngV', self.chrgngAddedElecRngV)
        self.add_optional_field_to_data(data, 'onBdChrgrAltrCrntInptCrnt', self.onBdChrgrAltrCrntInptCrnt)
        self.add_optional_field_to_data(data, 'onBdChrgrAltrCrntInptVol', self.onBdChrgrAltrCrntInptVol)
        self.add_optional_field_to_data(data, 'ccuOnbdChrgrPlugOn', self.ccuOnbdChrgrPlugOn)
        self.add_optional_field_to_data(data, 'ccuOffBdChrgrPlugOn', self.ccuOffBdChrgrPlugOn)
        self.add_optional_field_to_data(data, 'chrgngDoorPosSts', self.chrgngDoorPosSts)
        self.add_optional_field_to_data(data, 'chrgngDoorOpenCnd', self.chrgngDoorOpenCnd)
        return data

    def init_from_dict(self, data: dict):
        self.bmsReserCtrlDspCmd = data.get('bmsReserCtrlDspCmd')
        self.bmsReserStHourDspCmd = data.get('bmsReserStHourDspCmd')
        self.bmsReserStMintueDspCmd = data.get('bmsReserStMintueDspCmd')
        self.bmsReserSpHourDspCmd = data.get('bmsReserSpHourDspCmd')
        self.bmsReserSpMintueDspCmd = data.get('bmsReserSpMintueDspCmd')
        self.bmsOnBdChrgTrgtSOCDspCmd = data.get('bmsOnBdChrgTrgtSOCDspCmd')
        self.bms_estd_elec_rng = data.get('bmsEstdElecRng')
        self.bmsAltngChrgCrntDspCmd = data.get('bmsAltngChrgCrntDspCmd')
        self.bmsChrgCtrlDspCmd = data.get('bmsChrgCtrlDspCmd')
        self.chrgngRmnngTime = data.get('chrgngRmnngTime')
        self.chrgngRmnngTimeV = data.get('chrgngRmnngTimeV')
        self.bmsChrgOtptCrntReq = data.get('bmsChrgOtptCrntReq')
        self.bmsChrgOtptCrntReqV = data.get('bmsChrgOtptCrntReqV')
        self.bmsPackCrnt = data.get('bmsPackCrnt')
        self.bmsPackCrntV = data.get('bmsPackCrntV')
        self.bmsPackVol = data.get('bmsPackVol')
        self.bmsPackSOCDsp = data.get('bmsPackSOCDsp')
        self.bmsChrgSts = data.get('bmsChrgSts')
        self.bmsChrgSpRsn = data.get('bmsChrgSpRsn')
        self.clstrElecRngToEPT = data.get('clstrElecRngToEPT')
        self.bmsPTCHeatReqDspCmd = data.get('bmsPTCHeatReqDspCmd')
        self.bmsPTCHeatResp = data.get('bmsPTCHeatResp')
        self.ccuEleccLckCtrlDspCmd = data.get('ccuEleccLckCtrlDspCmd')
        self.bmsPTCHeatSpRsn = data.get('bmsPTCHeatSpRsn')
        self.bmsDsChrgSpRsn = data.get('bmsDsChrgSpRsn')
        self.disChrgngRmnngTime = data.get('disChrgngRmnngTime')
        self.disChrgngRmnngTimeV = data.get('disChrgngRmnngTimeV')
        self.imcuVehElecRng = data.get('imcuVehElecRng')
        self.imcuVehElecRngV = data.get('imcuVehElecRngV')
        self.imcuChrgngEstdElecRng = data.get('imcuChrgngEstdElecRng')
        self.imcuChrgngEstdElecRngV = data.get('imcuChrgngEstdElecRngV')
        self.imcuDschrgngEstdElecRng = data.get('imcuDschrgngEstdElecRng')
        self.imcuDschrgngEstdElecRngV = data.get('imcuDschrgngEstdElecRngV')
        self.chrgngSpdngTime = data.get('chrgngSpdngTime')
        self.chrgngSpdngTimeV = data.get('chrgngSpdngTimeV')
        self.chrgngAddedElecRng = data.get('chrgngAddedElecRng')
        self.chrgngAddedElecRngV = data.get('chrgngAddedElecRngV')
        self.onBdChrgrAltrCrntInptCrnt = data.get('onBdChrgrAltrCrntInptCrnt')
        self.onBdChrgrAltrCrntInptVol = data.get('onBdChrgrAltrCrntInptVol')
        self.ccuOnbdChrgrPlugOn = data.get('ccuOnbdChrgrPlugOn')
        self.ccuOffBdChrgrPlugOn = data.get('ccuOffBdChrgrPlugOn')
        self.chrgngDoorPosSts = data.get('chrgngDoorPosSts')
        self.chrgngDoorOpenCnd = data.get('chrgngDoorOpenCnd')
        self.chargeStatus = RvsChargingStatus()
        self.chargeStatus.init_from_dict(data.get('chargeStatus'))
        self.bmsAdpPubChrgSttnDspCmd = data.get('bmsAdpPubChrgSttnDspCmd')

    def get_current(self) -> float:
        return self.bmsPackCrnt * 0.05 - 1000.0

    def get_voltage(self) -> float:
        return self.bmsPackVol * 0.25

    def get_power(self) -> float:
        return self.get_current() * self.get_voltage() / 1000.0


class RvsChargingStatus(Asn1Type):
    def __init__(self):
        super().__init__('RvsChargingStatus')
        self.real_time_power = None  # INTEGER(0..65535),
        self.charging_gun_state = None  # BOOLEAN,
        self.fuel_Range_elec = None  # INTEGER(0..65535),
        self.charging_type = None  # INTEGER(0..255),
        self.start_time = None  # INTEGER(0..2147483647) OPTIONAL,
        self.end_time = None  # INTEGER(0..2147483647) OPTIONAL,
        self.charging_pile_id = None  # IA5String(SIZE(0..64)) OPTIONAL,
        self.charging_pile_supplier = None  # IA5String(SIZE(0..64)) OPTIONAL,
        self.working_current = None  # INTEGER(0..65535) OPTIONAL,
        self.working_voltage = None  # INTEGER(0..65535) OPTIONAL,
        self.mileage_since_last_charge = None  # INTEGER(0..65535) OPTIONAL,
        self.power_usage_since_last_charge = None  # INTEGER(0..65535) OPTIONAL,
        self.mileage_of_day = None  # INTEGER(0..65535) OPTIONAL,
        self.power_usage_of_day = None  # INTEGER(0..65535) OPTIONAL,
        self.static_energy_consumption = None  # INTEGER(0..65535) OPTIONAL,
        self.charging_electricity_phase = None  # INTEGER(0..255) OPTIONAL,
        self.charging_duration = None  # INTEGER(0..2147483647) OPTIONAL,
        self.last_charge_ending_power = None  # INTEGER(0..65535) OPTIONAL,
        self.total_battery_capacity = None  # INTEGER(0..65535) OPTIONAL,
        self.fota_lowest_voltage = None  # INTEGER(0..255) OPTIONAL,
        self.mileage = None  # INTEGER(0..2147483647),
        self.extended_data1 = None  # INTEGER(0..2147483647) OPTIONAL,
        self.extended_data2 = None  # INTEGER(0..2147483647) OPTIONAL,
        self.extended_data3 = None  # IA5String(SIZE(0..1024)) OPTIONAL,
        self.extended_data4 = None  # IA5String(SIZE(0..1024)) OPTIONAL

    def get_data(self) -> dict:
        data = {
            'realtimePower': self.real_time_power,
            'chargingGunState': self.charging_gun_state,
            'fuelRangeElec': self.fuel_Range_elec,
            'chargingType': self.charging_type,
            'mileage': self.mileage
        }
        self.add_optional_field_to_data(data, 'startTime', self.start_time)
        self.add_optional_field_to_data(data, 'endTime', self.end_time)
        self.add_optional_field_to_data(data, 'chargingPileID', self.charging_pile_id)
        self.add_optional_field_to_data(data, 'chargingPileSupplier', self.charging_pile_supplier)
        self.add_optional_field_to_data(data, 'workingCurrent', self.working_current)
        self.add_optional_field_to_data(data, 'workingVoltage', self.working_voltage)
        self.add_optional_field_to_data(data, 'mileageSinceLastCharge', self.mileage_since_last_charge)
        self.add_optional_field_to_data(data, 'powerUsageSinceLastCharge', self.power_usage_since_last_charge)
        self.add_optional_field_to_data(data, 'mileageOfDay', self.mileage_of_day)
        self.add_optional_field_to_data(data, 'powerUsageOfDay', self.power_usage_of_day)
        self.add_optional_field_to_data(data, 'staticEnergyConsumption', self.static_energy_consumption)
        self.add_optional_field_to_data(data, 'chargingElectricityPhase', self.charging_electricity_phase)
        self.add_optional_field_to_data(data, 'chargingDuration', self.charging_duration)
        self.add_optional_field_to_data(data, 'lastChargeEndingPower', self.last_charge_ending_power)
        self.add_optional_field_to_data(data, 'totalBatteryCapacity', self.total_battery_capacity)
        self.add_optional_field_to_data(data, 'fotaLowestVoltage', self.fota_lowest_voltage)
        self.add_optional_field_to_data(data, 'extendedData1', self.extended_data1)
        self.add_optional_field_to_data(data, 'extendedData2', self.extended_data2)
        self.add_optional_field_to_data(data, 'extendedData3', self.extended_data3)
        self.add_optional_field_to_data(data, 'extendedData4', self.extended_data4)
        return data

    def init_from_dict(self, data: dict) -> None:
        self.real_time_power = data.get('realtimePower')
        self.charging_gun_state = data.get('chargingGunState')
        self.fuel_Range_elec = data.get('fuelRangeElec')
        self.charging_type = data.get('chargingType')
        self.start_time = data.get('startTime')
        self.end_time = data.get('endTime')
        self.charging_pile_id = data.get('chargingPileID')
        self.charging_pile_supplier = data.get('chargingPileSupplier')
        self.working_current = data.get('workingCurrent')
        self.working_voltage = data.get('workingVoltage')
        self.mileage_since_last_charge = data.get('mileageSinceLastCharge')
        self.power_usage_since_last_charge = data.get('powerUsageSinceLastCharge')
        self.mileage_of_day = data.get('mileageOfDay')
        self.power_usage_of_day = data.get('powerUsageOfDay')
        self.static_energy_consumption = data.get('staticEnergyConsumption')
        self.charging_electricity_phase = data.get('chargingElectricityPhase')
        self.charging_duration = data.get('chargingDuration')
        self.last_charge_ending_power = data.get('lastChargeEndingPower')
        self.total_battery_capacity = data.get('totalBatteryCapacity')
        self.fota_lowest_voltage = data.get('fotaLowestVoltage')
        self.mileage = data.get('mileage')
        self.extended_data1 = data.get('extendedData1')
        self.extended_data2 = data.get('extendedData2')
        self.extended_data3 = data.get('extendedData3')
        self.extended_data4 = data.get('extendedData4')
