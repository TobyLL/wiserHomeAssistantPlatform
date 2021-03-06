"""
Drayton Wiser Compoment for Wiser System

Includes Climate and Sensor Devices

https://github.com/asantaga/wiserHomeAssistantPlatform
Angelo.santagata@gmail.com
"""
import asyncio
import json

# import time
from datetime import timedelta

from wiserHeatingAPI.wiserHub import wiserHub, TEMP_MINIMUM, TEMP_MAXIMUM
import voluptuous as vol

from homeassistant.const import (
    CONF_HOST,
    CONF_MINIMUM,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.util import Throttle

from .const import (
    _LOGGER,
    CONF_BOOST_TEMP,
    CONF_BOOST_TEMP_TIME,
    DOMAIN,
    NOTIFICATION_ID,
    NOTIFICATION_TITLE,
    VERSION,
    WISER_PLATFORMS,
)

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=30)

PLATFORM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_SCAN_INTERVAL, default=0): cv.time_period,
        vol.Optional(CONF_MINIMUM, default=TEMP_MINIMUM): vol.All(vol.Coerce(int)),
        vol.Optional(CONF_BOOST_TEMP, default=2): vol.All(vol.Coerce(int)),
        vol.Optional(CONF_BOOST_TEMP_TIME, default=30): vol.All(vol.Coerce(int)),
    }
)


async def async_setup(hass, config):

    host = config[DOMAIN][0][CONF_HOST]
    secret = config[DOMAIN][0][CONF_PASSWORD]
    scan_interval = config[DOMAIN][0][CONF_SCAN_INTERVAL]

    if scan_interval > timedelta(0):
        MIN_TIME_BETWEEN_UPDATES = scan_interval

    _LOGGER.info(
        "Wiser setup with Hub IP =  {} and scan interval of {}".format(
            host, MIN_TIME_BETWEEN_UPDATES
        )
    )

    data = WiserHubHandle(hass, config, host, secret)

    @callback
    def retryWiserHubSetup():
        hass.async_create_task(wiserHubSetup())
    
    async def wiserHubSetup():
        _LOGGER.info("Initiating WiserHub connection")
        try:
            if await data.async_update(no_throttle=True):
                if data.wiserhub.getDevices is None:
                    _LOGGER.error("No Wiser devices found to set up")
                    return False
            
                hass.data[DOMAIN] = data
            
                for component in WISER_PLATFORMS:
                    hass.async_create_task(async_load_platform(hass, component, DOMAIN, {}, config))
            
                _LOGGER.info("Wiser Component Setup Completed")
                return True
            else:
                await scheduleWiserHubSetup()
                return True
        except (asyncio.TimeoutError) as ex:
            await scheduleWiserHubSetup()
            return True
    
    async def scheduleWiserHubSetup(interval = 30):
        _LOGGER.error(
            "Unable to connect to the Wiser Hub, retrying in {} seconds".format(interval)
        )
        hass.loop.call_later(interval, retryWiserHubSetup)
        return
        
    hass.async_create_task(wiserHubSetup())
    return True
        



class WiserHubHandle:
    def __init__(self, hass, config, ip, secret):
        self._hass = hass
        self._config = config
        self.ip = ip
        self.secret = secret
        self.wiserhub = wiserHub(self.ip, self.secret)
        self.minimum_temp = TEMP_MINIMUM
        self.maximum_temp = TEMP_MAXIMUM
        self.boost_temp = self._config[DOMAIN][0][CONF_BOOST_TEMP]
        self.boost_time = self._config[DOMAIN][0][CONF_BOOST_TEMP_TIME]

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def async_update(self):
        _LOGGER.info("**Update of Wiser Hub data requested**")
        try:
            result = await self._hass.async_add_executor_job(self.wiserhub.refreshData)
            if result is not None:
                _LOGGER.info("**Wiser Hub data updated**")
                return True
            else:
                _LOGGER.info("**Unable to update from wiser hub**")
                return False
        except json.decoder.JSONDecodeError as JSONex:
            _LOGGER.error(
                "Data not JSON when getting Data from hub, "
                + "did you enter the right URL? error {}".format(str(JSONex))
            )
            self.hass.components.persistent_notification.create(
                "Error: {}"
                + "<br /> You will need to restart Home Assistant "
                + " after fixing.".format(JSONex),
                title=NOTIFICATION_TITLE,
                notification_id=NOTIFICATION_ID,
            )
            return False

    async def set_away_mode(self, away, away_temperature):
        mode = "AWAY" if away else "HOME"
        if self.wiserhub is None:
            self.wiserhub = wiserHub(self.ip, self.secret)
        _LOGGER.debug(
            "Setting away mode to {} with temp {}.".format(mode, away_temperature)
        )
        try:
            self.wiserhub.setHomeAwayMode(mode, away_temperature)
            await self.async_update(no_throttle=True)
        except BaseException as e:
            _LOGGER.debug("Error setting away mode! {}".format(str(e)))

    async def set_system_switch(self, switch, mode):
        if self.wiserhub is None:
            self.wiserhub = wiserHub(self.ip, self.secret)
        _LOGGER.debug(
            "Setting {} system switch to {}.".format(switch, "on" if mode else "off")
        )
        try:
            self.wiserhub.setSystemSwitch(switch, mode)
            await self.async_update(no_throttle=True)
        except BaseException as e:
            _LOGGER.debug("Error setting {} system switch! {}".format(switch, str(e)))


    async def set_smart_plug_state(self, plug_id, state):
        """
        Set the state of the smart plug,
        :param plug_id:
        :param state: Can be On or Off
        :return:
        """
        if self.wiserhub is None:
            self.wiserhub = wiserHub(self.ip, self.secret)
        _LOGGER.info(
            "Setting SmartPlug {} to {} ".format(plug_id, state))

        try:
            self.wiserhub.setSmartPlugState(plug_id,state)
            # Add small delay to allow hub to update status before refreshing
            await asyncio.sleep(0.5)
            await self.async_update(no_throttle=True)

        except BaseException as e:
            _LOGGER.debug("Error setting SmartPlug {} to {}, error {}".format(plug_id, state, str(e)))

    async def set_hotwater_mode(self, hotwater_mode):
        """

        """
        if self.wiserhub is None:
            self.wiserhub = wiserHub(self.ip, self.secret)
        _LOGGER.info(
            "Setting Hotwater to {} ".format(hotwater_mode))
        # Add small delay to allow hub to update status before refreshing
        await asyncio.sleep(0.5)
        await self.async_update(no_throttle=True)

        try:
            self.wiserhub.setHotwaterMode(hotwater_mode)


        except BaseException as e:
            _LOGGER.debug(
                "Error setting Hotwater Mode to  {}, error {}".format(hotwater_mode,
                                                                    str(e)))