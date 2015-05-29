#!/usr/bin/python
# -*- coding: utf-8 -*-

import subprocess
import os

from pcraster.framework import *
import pcraster as pcr

import logging
logger = logging.getLogger(__name__)

import waterBodies_for_modflow as waterBodies

import virtualOS as vos
from ncConverter import *

class GroundwaterModflow(object):
    
    def getState(self):
        result = {}
        
        # groundwater head (unit: m) for all layers
        for i in range(1, self.number_of_layers+1):
            var_name = 'groundwaterHeadLayer'+str(i)
            result[var_name] = vars(self)[var_name]
        
        return result


    def __init__(self, iniItems, landmask):
        object.__init__(self)
        
        # cloneMap, temporary directory for the resample process, temporary directory for the modflow process, absolute path for input directory, landmask
        self.cloneMap        = iniItems.cloneMap
        self.tmpDir          = iniItems.tmpDir
        self.tmp_modflow_dir = iniItems.tmp_modflow_dir
        self.inputDir        = iniItems.globalOptions['inputDir']
        self.landmask        = landmask
        
        # configuration from the ini file
        self.iniItems = iniItems
                
        # number of modflow layers:
        self.number_of_layers = int(iniItems.modflowParameterOptions['number_of_layers'])
        
        # topography properties: read several variables from the netcdf file
        for var in ['dem_minimum','dem_maximum','dem_average','dem_standard_deviation',\
                    'slopeLength','orographyBeta','tanslope',\
                    'dzRel0000','dzRel0001','dzRel0005',\
                    'dzRel0010','dzRel0020','dzRel0030','dzRel0040','dzRel0050',\
                    'dzRel0060','dzRel0070','dzRel0080','dzRel0090','dzRel0100']:
            vars(self)[var] = vos.netcdf2PCRobjCloneWithoutTime(self.iniItems.modflowParameterOptions['topographyNC'], \
                                                                var, self.cloneMap)
            vars(self)[var] = pcr.cover(vars(self)[var], 0.0)

        # channel properties: read several variables from the netcdf file
        for var in ['lddMap','cellAreaMap','gradient','bankfull_width',
                    'bankfull_depth','dem_floodplain','dem_riverbed']:
            vars(self)[var] = vos.netcdf2PCRobjCloneWithoutTime(self.iniItems.modflowParameterOptions['channelNC'], \
                                                                var, self.cloneMap)
            vars(self)[var] = pcr.cover(vars(self)[var], 0.0)
        
        # minimum channel width
        minimum_channel_width = 0.5                                               # TODO: Define this one in the configuration file
        self.bankfull_width = pcr.max(minimum_channel_width, self.bankfull_width)
        
        #~ # cell fraction if channel water reaching the flood plan               # NOT USED YET 
        #~ self.flood_plain_fraction = self.return_innundation_fraction(pcr.max(0.0, self.dem_floodplain - self.dem_minimum))
        
        # coefficient of Manning
        self.manningsN = vos.readPCRmapClone(self.iniItems.modflowParameterOptions['manningsN'],\
                                             self.cloneMap,self.tmpDir,self.inputDir)
        
        # minimum channel gradient
        minGradient   = 0.00005                                                   # TODO: Define this one in the configuration file
        self.gradient = pcr.max(minGradient, pcr.cover(self.gradient, minGradient))

        # correcting lddMap
        self.lddMap = pcr.ifthen(pcr.scalar(self.lddMap) > 0.0, self.lddMap)
        self.lddMap = pcr.lddrepair(pcr.ldd(self.lddMap))
        
        # channelLength = approximation of channel length (unit: m)  # This is approximated by cell diagonal. 
        cellSizeInArcMin      = np.round(pcr.clone().cellSize()*60.)               # FIXME: This one will not work if you use the resolution: 0.5, 1.5, 2.5 arc-min
        verticalSizeInMeter   = cellSizeInArcMin*1852.                            
        horizontalSizeInMeter = self.cellAreaMap/verticalSizeInMeter
        self.channelLength    = ((horizontalSizeInMeter)**(2)+\
                                 (verticalSizeInMeter)**(2))**(0.5)
        
        # option for lakes and reservoir
        self.onlyNaturalWaterBodies = False
        if self.iniItems.modflowParameterOptions['onlyNaturalWaterBodies'] == "True": self.onlyNaturalWaterBodies = True

        # groundwater linear recession coefficient (day-1) ; the linear reservoir concept is still being used to represent fast response flow  
        #                                                                                                                  particularly from karstic aquifer in mountainous regions                    
        self.recessionCoeff = vos.netcdf2PCRobjCloneWithoutTime(self.iniItems.modflowParameterOptions['groundwaterPropertiesNC'],\
                                                                 'recessionCoeff', self.cloneMap)
        self.recessionCoeff = pcr.cover(self.recessionCoeff,0.00)       
        self.recessionCoeff = pcr.min(1.0000,self.recessionCoeff)       
        #
        if 'minRecessionCoeff' in iniItems.modflowParameterOptions.keys():
            minRecessionCoeff = float(iniItems.modflowParameterOptions['minRecessionCoeff'])
        else:
            minRecessionCoeff = 1.0e-4                                       # This is the minimum value used in Van Beek et al. (2011). 
        self.recessionCoeff = pcr.max(minRecessionCoeff,self.recessionCoeff)      
        
        # aquifer saturated conductivity (m/day)
        self.kSatAquifer = vos.netcdf2PCRobjCloneWithoutTime(self.iniItems.modflowParameterOptions['groundwaterPropertiesNC'],\
                                                             'kSatAquifer', self.cloneMap)
        self.kSatAquifer = pcr.cover(self.kSatAquifer,pcr.mapmaximum(self.kSatAquifer))       
        self.kSatAquifer = pcr.max(0.001,self.kSatAquifer)
        # TODO: Define the minimum value as part of the configuration file
        
        # aquifer specific yield (dimensionless)
        self.specificYield = vos.netcdf2PCRobjCloneWithoutTime(self.iniItems.modflowParameterOptions['groundwaterPropertiesNC'],\
                                                               'specificYield', self.cloneMap)
        self.specificYield = pcr.cover(self.specificYield,pcr.mapmaximum(self.specificYield))       
        self.specificYield = pcr.max(0.010,self.specificYield)         # TODO: TO BE CHECKED: The resample process of specificYield     
        self.specificYield = pcr.min(1.000,self.specificYield)       
        # TODO: Define the minimum value as part of the configuration file

        # estimate of thickness (unit: m) of accesible groundwater 
        totalGroundwaterThickness = vos.netcdf2PCRobjCloneWithoutTime(self.iniItems.modflowParameterOptions['estimateOfTotalGroundwaterThicknessNC'],\
                                    'thickness', self.cloneMap)
        # extrapolation 
        totalGroundwaterThickness = pcr.cover(totalGroundwaterThickness,\
                                    pcr.windowaverage(totalGroundwaterThickness, 1.0))
        totalGroundwaterThickness = pcr.cover(totalGroundwaterThickness,\
                                    pcr.windowaverage(totalGroundwaterThickness, 1.5))
        totalGroundwaterThickness = pcr.cover(totalGroundwaterThickness, 0.0)
        #
        # set minimum thickness
        minimumThickness = pcr.scalar(float(\
                           self.iniItems.modflowParameterOptions['minimumTotalGroundwaterThickness']))
        totalGroundwaterThickness = pcr.max(minimumThickness, totalGroundwaterThickness)
        #
        # set maximum thickness: 250 m.   # TODO: Define this one as part of the ini file
        maximumThickness = 250.
        self.totalGroundwaterThickness = pcr.min(maximumThickness, totalGroundwaterThickness)
        # TODO: Define the maximum value as part of the configuration file

        # surface water bed thickness  (unit: m)
        bed_thickness  = 0.1              # TODO: Define this as part of the configuration file
        # surface water bed resistance (unit: day)
        bed_resistance = bed_thickness / (self.kSatAquifer) 
        minimum_bed_resistance = 1.0      # TODO: Define this as part of the configuration file
        self.bed_resistance = pcr.max(minimum_bed_resistance,\
                                              bed_resistance,)
        
        # option to ignore capillary rise
        self.ignoreCapRise = True
        if self.iniItems.modflowParameterOptions['ignoreCapRise'] == "False": self.ignoreCapRise = False
        
        # a variable to indicate if the modflow has been called or not
        self.modflow_has_been_called = False
        
        # list of the convergence criteria for HCLOSE (unit: m)
        # - Deltares default's value is 0.001 m                         # check this value with Jarno
        self.criteria_HCLOSE = [0.001, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]  
        self.criteria_HCLOSE = sorted(self.criteria_HCLOSE)
        
        # list of the convergence criteria for RCLOSE (unit: m3)
        # - Deltares default's value for their 25 and 250 m resolution models is 10 m3  # check this value with Jarno
        cell_area_assumption = verticalSizeInMeter * float(pcr.cellvalue(pcr.mapmaximum(horizontalSizeInMeter),1)[0])
        self.criteria_RCLOSE = [10., 10.* cell_area_assumption/(250.*250.), 10.* cell_area_assumption/(25.*25.)]
        self.criteria_RCLOSE = sorted(self.criteria_RCLOSE)

        # initiate the index for HCLOSE and RCLOSE
        self.iteration_HCLOSE = 0
        self.iteration_RCLOSE = 0
        
        # initiate old style reporting                                  # TODO: remove this!
        self.initiate_old_style_groundwater_reporting(iniItems)

    def initiate_modflow(self):

        logger.info("Initializing pcraster modflow.")
        
        # initialise pcraster modflow
        self.pcr_modflow = None
        self.pcr_modflow = pcr.initialise(pcr.clone())
        
        # setup the DIS package specifying the grids/layers used for the groundwater model
        # - Note the layer specification must start with the bottom layer (layer 1 is the lowermost layer)
        if self.number_of_layers == 1: self.set_grid_for_one_layer_model()
        if self.number_of_layers == 2: self.set_grid_for_two_layer_model()
         
        # specification for the boundary condition (ibound)
        # - active cells only in landmask
        # - constant head for outside the landmask
        ibound = pcr.ifthen(self.landmask, pcr.nominal(1))
        ibound = pcr.cover(ibound, pcr.nominal(-1))
        for i in range(1, self.number_of_layers+1): self.pcr_modflow.setBoundary(ibound, i)
        
        # setup the BCF package 
        if self.number_of_layers == 1: self.set_bcf_for_one_layer_model()
        if self.number_of_layers == 2: self.set_bcf_for_two_layer_model()

        # TODO: defining/incorporating anisotrophy values

    def set_grid_for_one_layer_model(self):

        # grid specification - one layer model
        top    = self.dem_average
        bottom = top - self.totalGroundwaterThickness
        self.pcr_modflow.createBottomLayer(bottom, top)
        
    def set_grid_for_two_layer_model(self):

        # grid specification - two layer model
        top_layer_2          = self.dem_average
        # - thickness of layer 1 is at least 10% of totalGroundwaterThickness
        bottom_layer_2       = self.dem_average - 0.10 * self.totalGroundwaterThickness
        # - thickness of layer 1 should be until 5 m below the river bed
        bottom_layer_2       = pcr.min(self.dem_riverbed - 5.0, bottom_layer_2)
        # - make sure that the minimum thickness of layer 2 is at least 0.1 m
        thickness_of_layer_2 = pcr.max(0.1, top_layer_2 - bottom_layer_2)
        bottom_layer_2       = top_layer_2 - thickness_of_layer_2
        # - thickness of layer 1 is at least 5.0 m
        thickness_of_layer_1 = pcr.max(5.0, self.totalGroundwaterThickness - thickness_of_layer_2)
        bottom_layer_1       = bottom_layer_2 - thickness_of_layer_1
        self.pcr_modflow.createBottomLayer(bottom_layer_1, bottom_layer_2)
        self.pcr_modflow.addLayer(top_layer_2)
        
        # layer thickness (m)
        self.thickness_of_layer_2 = thickness_of_layer_2
        self.thickness_of_layer_1 = thickness_of_layer_1

        # TODO: Incorporating the confining layer.

    def set_bcf_for_one_layer_model(self):

        # specification for conductivities (BCF package)
        horizontal_conductivity = self.kSatAquifer # unit: m/day
        # set the minimum value for transmissivity; (Deltares's default value: 10 m2/day)
        minimimumTransmissivity = 10.
        horizontal_conductivity = pcr.max(minimimumTransmissivity, \
                                          horizontal_conductivity * self.totalGroundwaterThickness) / self.totalGroundwaterThickness
        vertical_conductivity   = horizontal_conductivity               # dummy values, as one layer model is used
        self.pcr_modflow.setConductivity(00, horizontal_conductivity, \
                                             vertical_conductivity, 1)              

        # specification for storage coefficient
        # - correction due to the usage of lat/lon coordinates
        primary = pcr.cover(self.specificYield * self.cellAreaMap/(pcr.clone().cellSize()*pcr.clone().cellSize()), 0.0)
        primary = pcr.max(1e-10, primary)
        secondary = primary                                            # dummy values as we used the layer type 00
        self.pcr_modflow.setStorage(primary, secondary, 1)
        
    def set_bcf_for_two_layer_model(self):

        # specification for conductivities (BCF package)
        horizontal_conductivity = self.kSatAquifer # unit: m/day
        # set the minimum value for transmissivity; (Deltares's default value: 10 m2/day)
        minimimumTransmissivity = 10.

        # layer 2 (upper layer)
        horizontal_conductivity_layer_2 = pcr.max(minimimumTransmissivity, \
                                          horizontal_conductivity * self.thickness_of_layer_2) / self.thickness_of_layer_2
        vertical_conductivity_layer_2   = self.kSatAquifer * self.cellAreaMap/\
                                          (pcr.clone().cellSize()*pcr.clone().cellSize())
        self.pcr_modflow.setConductivity(00, horizontal_conductivity_layer_2, \
                                             vertical_conductivity_layer_2, 2)              
        
        # TODO: Incorporating the confining layer (e.g. specifying minimum value for vertical conductivity)

        # layer 1 (lower layer)
        horizontal_conductivity_layer_1 = pcr.max(minimimumTransmissivity, \
                                          horizontal_conductivity * self.thickness_of_layer_1) / self.thickness_of_layer_1
        vertical_conductivity_layer_1   = vertical_conductivity_layer_2    # dummy values 
        self.pcr_modflow.setConductivity(00, horizontal_conductivity_layer_1, \
                                             vertical_conductivity_layer_1, 1)              
        
        # specification for storage coefficient
        # - correction due to the usage of lat/lon coordinates
        primary = pcr.cover(self.specificYield * self.cellAreaMap/(pcr.clone().cellSize()*pcr.clone().cellSize()), 0.0)
        primary = pcr.max(1e-20, primary)
        secondary = primary                                           # dummy values as we used layer type 00
        self.pcr_modflow.setStorage(primary, secondary, 1)
        self.pcr_modflow.setStorage(primary, secondary, 2)

    def get_initial_heads(self):
		
        if self.iniItems.modflowTransientInputOptions['usingPredefinedInitialHead'] == "True": 
        
            # using pre-defined groundwater head(s) described in the ini/configuration file
            self.groundwaterHead = vos.readPCRmapClone(self.modflowTransientInputOptions['groundwaterHeadIni'],\
                                                       self.cloneMap, self.tmpDir, self.inputDir)

            # groundwater head (unit: m) for all layers
            for i in range(1, self.number_of_layers+1):
                var_name = 'groundwaterHeadLayer'+str(i)
                vars(self)[var_name] = vos.readPCRmapClone(self.modflowTransientInputOptions[var_name+'Ini'],\
                                                           self.cloneMap, self.tmpDir, self.inputDir)
                vars(self)[var_name] = pcr.cover(vars(self)[var_name], 0.0)                                           

        else:    

            # using the digital elevation model as the initial head
            for i in range(1, self.number_of_layers+1):
                var_name = 'groundwaterHeadLayer'+str(i)
                vars(self)[var_name] = self.dem_average

            # calculate/simulate a steady state condition (until the modflow converges)
            self.modflow_converged = False
            while self.modflow_converged == False:
                # get the current state(s) of groundwater head and put them in a dictionary
                groundwaterHead = self.getState()
                self.modflow_simulation("steady-state", groundwaterHead, None,1,1,self.criteria_HCLOSE[self.iteration_HCLOSE],\
                                                                                  self.criteria_RCLOSE[self.iteration_RCLOSE])
            
            # extrapolating the calculated heads for areas/cells outside the landmask (to remove isolated cells) 
            # 
            # - the calculate groundwater head within the landmask region
            for i in range(1, self.number_of_layers+1):
                var_name = 'groundwaterHeadLayer'+str(i)
                vars(self)[var_name] = pcr.ifthen(self.landmask, vars(self)[var_name])
                # keep the ocean values (dem <= 0.0) - this is in order to maintain the 'behaviors' of sub marine groundwater discharge
                vars(self)[var_name] = pcr.cover(vars(self)[var_name], pcr.ifthen(self.dem_average <= 0.0, self.dem_average))
                # extrapolation  
                vars(self)[var_name] = pcr.cover(vars(self)[var_name], pcr.windowaverage(vars(self)[var_name], 3.*pcr.clone().cellSize()))
                vars(self)[var_name] = pcr.cover(vars(self)[var_name], pcr.windowaverage(vars(self)[var_name], 5.*pcr.clone().cellSize()))
                vars(self)[var_name] = pcr.cover(vars(self)[var_name], pcr.windowaverage(vars(self)[var_name], 7.*pcr.clone().cellSize()))
                vars(self)[var_name] = pcr.cover(vars(self)[var_name], self.dem_average)
                # TODO: Define the window sizes as part of the configuration file. Also consider to use the inverse distance method. 
            
            # TODO: Also please consider to use Deltares's trick to remove isolated cells. 
        
        # after having the initial head, set the following variable to True to indicate the first month of the model simulation
        self.firstMonthOfSimulation = True      

    def estimate_bottom_of_bank_storage(self):

        # influence zone depth (m)  # TODO: Define this one as part of 
        influence_zone_depth = 5.0
        
        # bottom_elevation > flood_plain elevation - influence zone
        bottom_of_bank_storage = self.dem_floodplain - influence_zone_depth

        # reducing noise (so we will not introduce unrealistic sinks)      # TODO: Define the window size as part of the configuration/ini file
        bottom_of_bank_storage = pcr.max(bottom_of_bank_storage,\
                                 pcr.windowaverage(bottom_of_bank_storage, 3.0 * pcr.clone().cellSize()))

        # bottom_elevation > river bed
        bottom_of_bank_storage = pcr.max(self.dem_riverbed, bottom_of_bank_storage)
        
        # reducing noise by comparing to its downstream value (so we will not introduce unrealistic sinks)
        bottom_of_bank_storage = pcr.max(bottom_of_bank_storage, \
                                        (bottom_of_bank_storage +
                                         pcr.cover(pcr.downstream(self.lddMap, bottom_of_bank_storage), bottom_of_bank_storage))/2.)

        # bottom_elevation >= 0.0 (must be higher than sea level)
        bottom_of_bank_storage = pcr.max(0.0, bottom_of_bank_storage)
         
        # bottom_elevation < dem_average (this is to drain overland flow)
        bottom_of_bank_storage = pcr.min(bottom_of_bank_storage, self.dem_average)
        bottom_of_bank_storage = pcr.cover(bottom_of_bank_storage, self.dem_average)

        # define values only in landmask region
        bottom_of_bank_storage = pcr.ifthen(self.landmask, bottom_of_bank_storage)
        
        # TODO: Check again this concept. 
        
        # TODO: We may want to improve this concept - by incorporating the following:
        # - smooth bottom_elevation
        # - upstream areas in the mountainous regions and above perrenial stream starting points may also be drained (otherwise water will be accumulated and trapped there) 
        # - bottom_elevation > minimum elevation that is estimated from the maximum of S3 from the PCR-GLOBWB simulation
        
        return bottom_of_bank_storage

    def initiate_old_style_groundwater_reporting(self,iniItems):

        self.report = True
        try:
            self.outDailyTotNC = iniItems.oldReportingOptions['outDailyTotNC'].split(",")
            self.outMonthTotNC = iniItems.oldReportingOptions['outMonthTotNC'].split(",")
            self.outMonthAvgNC = iniItems.oldReportingOptions['outMonthAvgNC'].split(",")
            self.outMonthEndNC = iniItems.oldReportingOptions['outMonthEndNC'].split(",")
            self.outAnnuaTotNC = iniItems.oldReportingOptions['outAnnuaTotNC'].split(",")
            self.outAnnuaAvgNC = iniItems.oldReportingOptions['outAnnuaAvgNC'].split(",")
            self.outAnnuaEndNC = iniItems.oldReportingOptions['outAnnuaEndNC'].split(",")
        except:
            self.report = False
        if self.report == True:
            self.outNCDir  = iniItems.outNCDir
            self.netcdfObj = PCR2netCDF(iniItems)
            #
            # daily output in netCDF files:
            if self.outDailyTotNC[0] != "None":
                for var in self.outDailyTotNC:
                    # creating the netCDF files:
                    self.netcdfObj.createNetCDF(str(self.outNCDir)+"/"+ \
                                                str(var)+"_dailyTot.nc",\
                                                    var,"undefined")
            # MONTHly output in netCDF files:
            # - cummulative
            if self.outMonthTotNC[0] != "None":
                for var in self.outMonthTotNC:
                    # initiating monthlyVarTot (accumulator variable):
                    vars(self)[var+'MonthTot'] = None
                    # creating the netCDF files:
                    self.netcdfObj.createNetCDF(str(self.outNCDir)+"/"+ \
                                                str(var)+"_monthTot.nc",\
                                                    var,"undefined")
            # - average
            if self.outMonthAvgNC[0] != "None":
                for var in self.outMonthAvgNC:
                    # initiating monthlyTotAvg (accumulator variable)
                    vars(self)[var+'MonthTot'] = None
                    # initiating monthlyVarAvg:
                    vars(self)[var+'MonthAvg'] = None
                     # creating the netCDF files:
                    self.netcdfObj.createNetCDF(str(self.outNCDir)+"/"+ \
                                                str(var)+"_monthAvg.nc",\
                                                    var,"undefined")
            # - last day of the month
            if self.outMonthEndNC[0] != "None":
                for var in self.outMonthEndNC:
                     # creating the netCDF files:
                    self.netcdfObj.createNetCDF(str(self.outNCDir)+"/"+ \
                                                str(var)+"_monthEnd.nc",\
                                                    var,"undefined")
            # YEARly output in netCDF files:
            # - cummulative
            if self.outAnnuaTotNC[0] != "None":
                for var in self.outAnnuaTotNC:
                    # initiating yearly accumulator variable:
                    vars(self)[var+'AnnuaTot'] = None
                    # creating the netCDF files:
                    self.netcdfObj.createNetCDF(str(self.outNCDir)+"/"+ \
                                                str(var)+"_annuaTot.nc",\
                                                    var,"undefined")
            # - average
            if self.outAnnuaAvgNC[0] != "None":
                for var in self.outAnnuaAvgNC:
                    # initiating annualyVarAvg:
                    vars(self)[var+'AnnuaAvg'] = None
                    # initiating annualyTotAvg (accumulator variable)
                    vars(self)[var+'AnnuaTot'] = None
                     # creating the netCDF files:
                    self.netcdfObj.createNetCDF(str(self.outNCDir)+"/"+ \
                                                str(var)+"_annuaAvg.nc",\
                                                    var,"undefined")
            # - last day of the year
            if self.outAnnuaEndNC[0] != "None":
                for var in self.outAnnuaEndNC:
                     # creating the netCDF files:
                    self.netcdfObj.createNetCDF(str(self.outNCDir)+"/"+ \
                                                str(var)+"_annuaEnd.nc",\
                                                    var,"undefined")


    def update(self,currTimeStep):

        # at the end of the month, calculate/simulate a steady state condition and obtain its calculated head values
        if currTimeStep.isLastDayOfMonth():
            # calculate modflow until it converges
            self.modflow_converged = False
            groundwaterHead = self.getState()
            while self.modflow_converged == False: self.modflow_simulation("transient",groundwaterHead,currTimeStep,currTimeStep.day,currTimeStep.day,self.criteria_HCLOSE[self.iteration_HCLOSE],\
                                                                                                                                                      self.criteria_RCLOSE[self.iteration_RCLOSE])

    def modflow_simulation(self,\
                           simulation_type,\
                           initialGroundwaterHeadInADictionary,\
                           currTimeStep = None,\
                           PERLEN = 1.0, 
                           NSTP   = 1, \
                           HCLOSE = 1.0,\
                           RCLOSE = 10.* 400.*400.,\
                           MXITER = 50,\
                           ITERI = 30,\
                           NPCOND = 1,\
                           RELAX = 1.00,\
                           NBPOL = 2,\
                           DAMP = 1,\
                           ITMUNI = 4, LENUNI = 2, TSMULT = 1.0):
        
        # initiate pcraster modflow object if modflow is not called yet:
        if self.modflow_has_been_called == False or self.modflow_converged == False:
            self.initiate_modflow()
            self.modflow_has_been_called = True

        if simulation_type == "transient":
            logger.info("Preparing MODFLOW input for a transient simulation.")
            SSTR = 0
        if simulation_type == "steady-state":
            logger.info("Preparing MODFLOW input for a steady-state simulation.")
            SSTR = 1

        # waterBody class to define the extent of lakes and reservoirs
        #
        if simulation_type == "steady-state":
            self.WaterBodies = waterBodies.WaterBodies(self.iniItems,\
                                                       self.landmask,\
                                                       self.onlyNaturalWaterBodies)
            self.WaterBodies.getParameterFiles(date_given = self.iniItems.globalOptions['startTime'],\
                                               cellArea = self.cellAreaMap, \
                                               ldd = self.lddMap)        
        #
        if simulation_type == "transient":
            if currTimeStep.timeStepPCR == 1:
               self.WaterBodies = waterBodies.WaterBodies(self.iniItems,\
                                                          self.landmask,\
                                                          self.onlyNaturalWaterBodies)
            if currTimeStep.timeStepPCR == 1 or currTimeStep.doy == 1:
               self.WaterBodies.getParameterFiles(date_given = str(currTimeStep.fulldate),\
                                                  cellArea = self.cellAreaMap, \
                                                  ldd = self.lddMap)        

        # extract and set initial head for modflow simulation
        groundwaterHead = initialGroundwaterHeadInADictionary
        for i in range(1, self.number_of_layers+1):
            var_name = 'groundwaterHeadLayer'+str(i)
            initial_head = pcr.scalar(groundwaterHead[var_name])
            self.pcr_modflow.setInitialHead(initial_head, i)
        
        # set parameter values for the DIS package and PCG solver
        self.pcr_modflow.setDISParameter(ITMUNI, LENUNI, PERLEN, NSTP, TSMULT, SSTR)
        self.pcr_modflow.setPCG(MXITER, ITERI, NPCOND, HCLOSE, RCLOSE, RELAX, NBPOL, DAMP)
        #
        # Some notes about the values  
        #
        # ITMUNI = 4     # indicates the time unit (0: undefined, 1: seconds, 2: minutes, 3: hours, 4: days, 5: years)
        # LENUNI = 2     # indicates the length unit (0: undefined, 1: feet, 2: meters, 3: centimeters)
        # PERLEN = 1.0   # duration of a stress period
        # NSTP   = 1     # number of time steps in a stress period
        # TSMULT = 1.0   # multiplier for the length of the successive iterations
        # SSTR   = 1     # 0 - transient, 1 - steady state
        #
        # MXITER = 50                 # maximum number of outer iterations           # Deltares use 50
        # ITERI  = 30                 # number of inner iterations                   # Deltares use 30
        # NPCOND = 1                  # 1 - Modified Incomplete Cholesky, 2 - Polynomial matrix conditioning method;
        # HCLOSE = 0.01               # HCLOSE (unit: m) 
        # RCLOSE = 10.* 400.*400.     # RCLOSE (unit: m3)
        # RELAX  = 1.00               # relaxation parameter used with NPCOND = 1
        # NBPOL  = 2                  # indicates whether the estimate of the upper bound on the maximum eigenvalue is 2.0 (but we don ot use it, since NPCOND = 1) 
        # DAMP   = 1                  # no damping (DAMP introduced in MODFLOW 2000)
        
        # read input files (for the steady-state condition, we use pcraster maps):
        if simulation_type == "steady-state":
            # - discharge (m3/s) from PCR-GLOBWB
            discharge = vos.readPCRmapClone(self.iniItems.modflowSteadyStateInputOptions['avgDischargeInputMap'],\
                                                self.cloneMap, self.tmpDir, self.inputDir)
            # - recharge/capillary rise (unit: m/day) from PCR-GLOBWB 
            gwRecharge = vos.readPCRmapClone(self.iniItems.modflowSteadyStateInputOptions['avgGroundwaterRechargeInputMap'],\
                                                self.cloneMap, self.tmpDir, self.inputDir)
            if self.ignoreCapRise: gwRecharge = pcr.max(0.0, gwRecharge) 
            gwAbstraction = pcr.spatial(pcr.scalar(0.0))

        # read input files (for the transient, input files are given in netcdf files):
        if simulation_type == "transient":
            # - discharge (m3/s) from PCR-GLOBWB
            discharge = vos.netcdf2PCRobjClone(self.iniItems.modflowTransientInputOptions['dischargeInputNC'],
                                               "discharge",str(currTimeStep.fulldate),None,self.cloneMap)
            # - recharge/capillary rise (unit: m/day) from PCR-GLOBWB 
            gwRecharge = vos.netcdf2PCRobjClone(self.iniItems.modflowTransientInputOptions['groundwaterRechargeInputNC'],\
                                               "groundwater_recharge",str(currTimeStep.fulldate),None,self.cloneMap)
            if self.ignoreCapRise: gwRecharge = pcr.max(0.0, gwRecharge) 
            # - groundwater abstraction (unit: m/day) from PCR-GLOBWB 
            gwAbstraction = vos.netcdf2PCRobjClone(self.iniItems.modflowTransientInputOptions['groundwaterAbstractionInputNC'],\
                                               "total_groundwater_abstraction",str(currTimeStep.fulldate),None,self.cloneMap)

        # set recharge, river, well and drain packages
        self.set_river_package(discharge, currTimeStep)
        self.set_recharge_package(gwRecharge)
        self.set_well_package(gwAbstraction)
        self.set_drain_package()
        
        # execute MODFLOW 
        logger.info("Executing MODFLOW.")
        self.pcr_modflow.run()
        
        logger.info("Check if the model whether a run has converged or not")
        self.modflow_converged = self.check_modflow_convergence()
        if self.modflow_converged == False:

            msg = "MODFLOW FAILED TO CONVERGE with HCLOSE = "+str(HCLOSE)+" and RCLOSE = "+str(RCLOSE)
            logger.info(msg)
            
            # iteration index for the RCLOSE
            self.iteration_RCLOSE += 1 
            # reset if the index has reached the length of available criteria
            if self.iteration_RCLOSE > (len(self.criteria_RCLOSE)-1): self.iteration_RCLOSE = 0     

            # iteration index for the HCLOSE
            if self.iteration_RCLOSE == 0: self.iteration_HCLOSE += 1 
            
            # we have to reset modflow as we want to change the PCG setup
            self.modflow_has_been_called = False
            
            # for the steady state simulation, we still save the calculated head as the initial estimate for the next iteration
            if simulation_type == "steady-state": 
                for i in range(1, self.number_of_layers+1):
                    var_name = 'groundwaterHeadLayer'+str(i)
                    vars(self)[var_name] = None
                    vars(self)[var_name] = self.pcr_modflow.getHeads(i)
            # NOTE: We should not implement this principle for a transient simulation result that does not converge.
            
        else:

            msg = "HURRAY!!! MODFLOW CONVERGED with HCLOSE = "+str(HCLOSE)+" and RCLOSE = "+str(RCLOSE)
            logger.info(msg)

            # reset the iteration because modflow has converged
            self.iteration_HCLOSE = 0
            self.iteration_RCLOSE = 0
            
            self.modflow_has_been_called = True
            
            # obtaining the results from modflow simulation
            for i in range(1, self.number_of_layers+1):
                # groundwater head (unit: m)
                var_head_name = 'groundwaterHeadLayer'+str(i)
                vars(self)[var_head_name] = None
                vars(self)[var_head_name] = self.pcr_modflow.getHeads(i)
                # calculate groundwater depth (unit: m), only in the landmask region
                var_depth_name = 'groundwaterDepthLayer'+str(i)
                vars(self)[var_depth_name] = pcr.ifthen(self.landmask, self.dem_average - vars(self)[var_head_name])
            
            # for debuging only
            pcr.report(self.groundwaterHeadLayer1 , "gw_head_bottom.map")
            pcr.report(self.groundwaterDepthLayer1, "gw_depth_bottom.map")

    def check_modflow_convergence(self, file_name = "pcrmf.lst"):
        
        # open and read the lst file
        file_name = self.tmp_modflow_dir+"/"+file_name
        f = open(file_name) ; all_lines = f.read() ; f.close()
        
        # split the content of the file into several lines
        all_lines = all_lines.replace("\r","") 
        all_lines = all_lines.split("\n")
        
        # scan the last 200 lines and check if the model 
        modflow_converged = True
        for i in range(0,200): 
            if 'FAILED TO CONVERGE' in all_lines[-i]: modflow_converged = False
        
        return modflow_converged    

    def set_river_package(self, discharge, currTimeStep):

        logger.info("Set the river package.")
        
        # - surface water river bed/bottom elevation and conductance 
        need_to_define_surface_water_bed = False
        if currTimeStep == None:
            # this is for a steady state simulation (no currTimeStep define)
            need_to_define_surface_water_bed = True
        else:    
            # only at the first month of the model simulation or the first month of the year
            if self.firstMonthOfSimulation or currTimeStep.month == 1:
                need_to_define_surface_water_bed = True
                self.firstMonthOfSimulation = False          # This part becomes False as we don't need it anymore. 

        if need_to_define_surface_water_bed:

            logger.info("Estimating the surface water bed elevation and surface water bed conductance.")
        
            #~ # - for lakes and resevoirs, alternative 1: make the bottom elevation deep --- Shall we do this? 
            #~ additional_depth = 500.
            #~ surface_water_bed_elevation = pcr.ifthen(pcr.scalar(self.WaterBodies.waterBodyIds) > 0.0, \
                                                     #~ self.dem_riverbed - additional_depth)
            #
            # - for lakes and resevoirs, estimate bed elevation from dem and bankfull depth
            surface_water_bed_elevation  = pcr.ifthen(pcr.scalar(self.WaterBodies.waterBodyIds) > 0.0, self.dem_average)
            surface_water_bed_elevation  = pcr.areaaverage(surface_water_bed_elevation, self.WaterBodies.waterBodyIds)
            surface_water_bed_elevation -= pcr.areamaximum(self.bankfull_depth, self.WaterBodies.waterBodyIds) 
            #
            surface_water_bed_elevation  = pcr.cover(surface_water_bed_elevation, self.dem_riverbed)
            #~ surface_water_bed_elevation = self.dem_riverbed # This is an alternative, if we do not want to introduce very deep bottom elevations of lakes and/or reservoirs.   
            #
            # rounding values for surface_water_bed_elevation
            self.surface_water_bed_elevation = pcr.roundup(surface_water_bed_elevation * 1000.)/1000.
            #
            # - river bed condutance (unit: m2/day)
            bed_surface_area = pcr.ifthen(pcr.scalar(self.WaterBodies.waterBodyIds) > 0.0, \
                                                     self.WaterBodies.fracWat * self.cellAreaMap)   # TODO: Incorporate the concept of dynamicFracWat # I have problem with the convergence if I use this one. 
            bed_surface_area = pcr.min(bed_surface_area,\
                               pcr.ifthen(pcr.scalar(self.WaterBodies.waterBodyIds) > 0.0, \
                                          pcr.areaaverage(self.bankfull_width * self.channelLength, self.WaterBodies.waterBodyIds)))
            bed_surface_area = pcr.cover(bed_surface_area, \
                                         self.bankfull_width * self.channelLength)
            #~ bed_surface_area = self.bankfull_width * self.channelLength
            bed_conductance = (1.0/self.bed_resistance) * bed_surface_area
            bed_conductance = pcr.ifthenelse(bed_conductance < 1e-20, 0.0, \
                                             bed_conductance) 
            self.bed_conductance = pcr.cover(bed_conductance, 0.0)
             

            logger.info("Estimating outlet widths of lakes and/or reservoirs.")
            # - 'channel width' for lakes and reservoirs 
            channel_width = pcr.areamaximum(self.bankfull_width, self.WaterBodies.waterBodyIds)
            self.channel_width = pcr.cover(channel_width, self.bankfull_width)
        

        logger.info("Estimating surface water elevation.")
        
        # - convert discharge value to surface water elevation (m)
        river_water_height = (self.channel_width**(-3/5)) * (discharge**(3/5)) * ((self.gradient)**(-3/10)) *(self.manningsN**(3/5))
        surface_water_elevation = self.dem_riverbed + \
                                  river_water_height
        #
        # - calculating water level (unit: m) above the flood plain   # TODO: Improve this concept (using Rens's latest innundation scheme) 
        #----------------------------------------------------------
        water_above_fpl  = pcr.max(0.0, surface_water_elevation - self.dem_floodplain)  # unit: m, water level above the floodplain (not distributed)
        water_above_fpl *= self.bankfull_depth * self.bankfull_width / self.cellAreaMap  # unit: m, water level above the floodplain (distributed within the cell)
        # TODO: Improve this concept using Rens's latest scheme
        #
        # - corrected surface water elevation
        surface_water_elevation = pcr.ifthenelse(surface_water_elevation > self.dem_floodplain, \
                                                                           self.dem_floodplain + water_above_fpl, \
                                                                           surface_water_elevation)
        # - surface water elevation for lakes and reservoirs:
        lake_reservoir_water_elevation = pcr.ifthen(self.WaterBodies.waterBodyOut, surface_water_elevation)
        lake_reservoir_water_elevation = pcr.areamaximum(lake_reservoir_water_elevation, self.WaterBodies.waterBodyIds)
        lake_reservoir_water_elevation = pcr.cover(lake_reservoir_water_elevation, \
                                         pcr.areaaverage(surface_water_elevation, self.WaterBodies.waterBodyIds))
        # - maximum and minimum values for lake_reservoir_water_elevation
        lake_reservoir_water_elevation = pcr.min(self.dem_floodplain, lake_reservoir_water_elevation)
        lake_reservoir_water_elevation = pcr.max(self.surface_water_bed_elevation, lake_reservoir_water_elevation)
        # - smoothing
        lake_reservoir_water_elevation = pcr.areaaverage(surface_water_elevation, self.WaterBodies.waterBodyIds)
        # 
        # - merge lake and reservoir water elevation
        surface_water_elevation = pcr.cover(lake_reservoir_water_elevation, surface_water_elevation)
        #
        # - covering the missing values and rounding
        surface_water_elevation = pcr.cover(surface_water_elevation, self.surface_water_bed_elevation)
        surface_water_elevation = pcr.rounddown(surface_water_elevation * 1000.)/1000.
        #
        # - make sure that HRIV >= RBOT ; no infiltration if HRIV = RBOT (and h < RBOT)  
        self.surface_water_elevation = pcr.max(surface_water_elevation, self.surface_water_bed_elevation)
        #
        #~ # reducing the size of table by ignoring cells with zero conductance and outside the landmask regions           # FIXME: Oliver should fix this. 
        #~ self.bed_conductance = pcr.ifthen(self.landmask, self.bed_conductance)
        #~ self.bed_conductance = pcr.ifthen(self.bed_conductance > 0.0, self.bed_conductance)
        #~ self.surface_water_elevation = pcr.ifthen(self.bed_conductance > 0.0, self.surface_water_elevation)
        #~ self.surface_water_bed_elevation = pcr.ifthen(self.bed_conductance > 0.0, self.surface_water_bed_elevation)
        #
        # set the RIV package only to the uppermost layer
        self.pcr_modflow.setRiver(self.surface_water_elevation, self.surface_water_bed_elevation, self.bed_conductance, self.number_of_layers)
        
        # TODO: Improve the concept of RIV package, particularly while calculating surface water elevation in lakes and reservoirs
        
    def set_recharge_package(self, \
                             gwRecharge, gwAbstraction = 0.0, 
                             gwAbstractionReturnFlow = 0.0):            # Note: We ignored the latter as MODFLOW should capture this part as well.
								                                        #       We also moved the abstraction to the WELL package 

        logger.info("Set the recharge package.")

        # specify the recharge package
        # + recharge/capillary rise (unit: m/day) from PCR-GLOBWB 
        # - groundwater abstraction (unit: m/day) from PCR-GLOBWB 
        # + return flow of groundwater abstraction (unit: m/day) from PCR-GLOBWB 
        net_recharge = gwRecharge - gwAbstraction + \
                       gwAbstractionReturnFlow

        # - correcting values (considering MODFLOW lat/lon cell properties)
        #   and pass them to the RCH package   
        net_RCH = pcr.cover(net_recharge * self.cellAreaMap/(pcr.clone().cellSize()*pcr.clone().cellSize()), 0.0)
        net_RCH = pcr.cover(pcr.ifthenelse(pcr.abs(net_RCH) < 1e-20, 0.0, net_RCH), 0.0)
        
        # put the recharge to the top grid/layer
        self.pcr_modflow.setRecharge(net_RCH, 1)

    def set_well_package(self, gwAbstraction):
        
        logger.info("Set the well package.")

        # reducing the size of table by ignoring cells with zero abstraction
        gwAbstraction = pcr.ifthen(gwAbstraction > 0.0, gwAbstraction)

        # abstraction volume (negative value, unit: m3/day)
        abstraction = gwAbstraction * self.cellAreaMap * pcr.scalar(-1.0)
        
        # FIXME: The following cover operations should not be necessary (Oliver should fix this).
        abstraction = pcr.cover(gwAbstraction, 0.0) 
        
        # set the well based on number of layers
        if self.number_of_layers == 1: self.pcr_modflow.setWell(abstraction, 1)
        if self.number_of_layers == 2: self.pcr_modflow.setWell(abstraction, 1)                # at the bottom layer


    def set_drain_package(self):

        logger.info("Set the drain package (for the release of over bank storage).")

        # specify the drain package the drain package is used to simulate the drainage of bank storage 

        # - estimate bottom of bank stoarage for flood plain areas
        drain_elevation = self.estimate_bottom_of_bank_storage()                               # unit: m
        # - for lakes and/or reservoirs, ignore the drainage
        drain_conductance = pcr.ifthen(pcr.scalar(self.WaterBodies.waterBodyIds) > 0.0, pcr.scalar(0.0))
        # - drainage conductance is a linear reservoir coefficient
        drain_conductance = pcr.cover(drain_conductance, \
                            self.recessionCoeff * self.specificYield * self.cellAreaMap)       # unit: m2/day

        # reducing the size of table by ignoring cells with zero conductance
        drain_conductance = pcr.ifthen(drain_conductance > 0.0, drain_conductance)
        drain_elevation   = pcr.ifthen(drain_elevation   > 0.0, drain_elevation)

        # FIXME: The following cover operations should not be necessary (Oliver should fix this).
        drain_conductance = pcr.cover(drain_conductance, 0.0)
        drain_elevation   = pcr.cover(drain_elevation  , 0.0)
        
        # set the DRN package only to the uppermost layer               # TODO: We may want to introduce this to all layers
        self.pcr_modflow.setDrain(drain_elevation, drain_conductance, self.number_of_layers)

    def return_innundation_fraction(self,relative_water_height):

        # - fractions of flooded area (in percentage) based on the relative_water_height (above the minimum dem)
        DZRIV = relative_water_height
        
        CRFRAC_RIV =                         pcr.min(1.0,1.00-(self.dzRel0100-DZRIV)*0.10/pcr.max(1e-3,self.dzRel0100-self.dzRel0090)       	 )
        CRFRAC_RIV = pcr.ifthenelse(DZRIV<self.dzRel0090,0.90-(self.dzRel0090-DZRIV)*0.10/pcr.max(1e-3,self.dzRel0090-self.dzRel0080),CRFRAC_RIV )
        CRFRAC_RIV = pcr.ifthenelse(DZRIV<self.dzRel0080,0.80-(self.dzRel0080-DZRIV)*0.10/pcr.max(1e-3,self.dzRel0080-self.dzRel0070),CRFRAC_RIV )
        CRFRAC_RIV = pcr.ifthenelse(DZRIV<self.dzRel0070,0.70-(self.dzRel0070-DZRIV)*0.10/pcr.max(1e-3,self.dzRel0070-self.dzRel0060),CRFRAC_RIV )
        CRFRAC_RIV = pcr.ifthenelse(DZRIV<self.dzRel0060,0.60-(self.dzRel0060-DZRIV)*0.10/pcr.max(1e-3,self.dzRel0060-self.dzRel0050),CRFRAC_RIV )
        CRFRAC_RIV = pcr.ifthenelse(DZRIV<self.dzRel0050,0.50-(self.dzRel0050-DZRIV)*0.10/pcr.max(1e-3,self.dzRel0050-self.dzRel0040),CRFRAC_RIV )
        CRFRAC_RIV = pcr.ifthenelse(DZRIV<self.dzRel0040,0.40-(self.dzRel0040-DZRIV)*0.10/pcr.max(1e-3,self.dzRel0040-self.dzRel0030),CRFRAC_RIV )
        CRFRAC_RIV = pcr.ifthenelse(DZRIV<self.dzRel0030,0.30-(self.dzRel0030-DZRIV)*0.10/pcr.max(1e-3,self.dzRel0030-self.dzRel0020),CRFRAC_RIV )
        CRFRAC_RIV = pcr.ifthenelse(DZRIV<self.dzRel0020,0.20-(self.dzRel0020-DZRIV)*0.10/pcr.max(1e-3,self.dzRel0020-self.dzRel0010),CRFRAC_RIV )
        CRFRAC_RIV = pcr.ifthenelse(DZRIV<self.dzRel0010,0.10-(self.dzRel0010-DZRIV)*0.05/pcr.max(1e-3,self.dzRel0010-self.dzRel0005),CRFRAC_RIV )
        CRFRAC_RIV = pcr.ifthenelse(DZRIV<self.dzRel0005,0.05-(self.dzRel0005-DZRIV)*0.04/pcr.max(1e-3,self.dzRel0005-self.dzRel0001),CRFRAC_RIV )
        CRFRAC_RIV = pcr.ifthenelse(DZRIV<self.dzRel0001,0.01-(self.dzRel0001-DZRIV)*0.01/pcr.max(1e-3,self.dzRel0001)               ,CRFRAC_RIV )
        CRFRAC_RIV = pcr.ifthenelse(DZRIV<=0,0, CRFRAC_RIV)
        
        # - minimum value of innundation fraction is river/channel area
        CRFRAC_RIV = pcr.cover(pcr.max(0.0,pcr.min(1.0,pcr.max(CRFRAC_RIV,(self.bankfull_depth*self.bankfull_width/self.cellAreaMap)))),scalar(0))		;

        # TODO: Improve this concept using Rens's latest scheme

    def old_style_groundwater_reporting(self,currTimeStep):

        if self.report == True:
            timeStamp = datetime.datetime(currTimeStep.year,\
                                          currTimeStep.month,\
                                          currTimeStep.day,\
                                          0)
            # writing daily output to netcdf files
            timestepPCR = currTimeStep.timeStepPCR
            if self.outDailyTotNC[0] != "None":
                for var in self.outDailyTotNC:
                    self.netcdfObj.data2NetCDF(str(self.outNCDir)+"/"+ \
                                         str(var)+"_dailyTot.nc",\
                                         var,\
                          pcr2numpy(self.__getattribute__(var),vos.MV),\
                                         timeStamp,timestepPCR-1)

            # writing monthly output to netcdf files
            # -cummulative
            if self.outMonthTotNC[0] != "None":
                for var in self.outMonthTotNC:

                    # introduce variables at the beginning of simulation or
                    #     reset variables at the beginning of the month
                    if currTimeStep.timeStepPCR == 1 or \
                       currTimeStep.day == 1:\
                       vars(self)[var+'MonthTot'] = pcr.scalar(0.0)

                    # accumulating
                    vars(self)[var+'MonthTot'] += vars(self)[var]

                    # reporting at the end of the month:
                    if currTimeStep.endMonth == True: 
                        self.netcdfObj.data2NetCDF(str(self.outNCDir)+"/"+ \
                                         str(var)+"_monthTot.nc",\
                                         var,\
                          pcr2numpy(self.__getattribute__(var+'MonthTot'),\
                           vos.MV),timeStamp,currTimeStep.monthIdx-1)
            # -average
            if self.outMonthAvgNC[0] != "None":
                for var in self.outMonthAvgNC:
                    # only if a accumulator variable has not been defined: 
                    if var not in self.outMonthTotNC: 

                        # introduce accumulator at the beginning of simulation or
                        #     reset accumulator at the beginning of the month
                        if currTimeStep.timeStepPCR == 1 or \
                           currTimeStep.day == 1:\
                           vars(self)[var+'MonthTot'] = pcr.scalar(0.0)
                        # accumulating
                        vars(self)[var+'MonthTot'] += vars(self)[var]

                    # calculating average & reporting at the end of the month:
                    if currTimeStep.endMonth == True:
                        vars(self)[var+'MonthAvg'] = vars(self)[var+'MonthTot']/\
                                                     currTimeStep.day  
                        self.netcdfObj.data2NetCDF(str(self.outNCDir)+"/"+ \
                                         str(var)+"_monthAvg.nc",\
                                         var,\
                          pcr2numpy(self.__getattribute__(var+'MonthAvg'),\
                           vos.MV),timeStamp,currTimeStep.monthIdx-1)
            #
            # -last day of the month
            if self.outMonthEndNC[0] != "None":
                for var in self.outMonthEndNC:
                    # reporting at the end of the month:
                    if currTimeStep.endMonth == True: 
                        self.netcdfObj.data2NetCDF(str(self.outNCDir)+"/"+ \
                                         str(var)+"_monthEnd.nc",\
                                         var,\
                          pcr2numpy(self.__getattribute__(var),vos.MV),\
                                         timeStamp,currTimeStep.monthIdx-1)

            # writing yearly output to netcdf files
            # -cummulative
            if self.outAnnuaTotNC[0] != "None":
                for var in self.outAnnuaTotNC:

                    # introduce variables at the beginning of simulation or
                    #     reset variables at the beginning of the month
                    if currTimeStep.timeStepPCR == 1 or \
                       currTimeStep.doy == 1:\
                       vars(self)[var+'AnnuaTot'] = pcr.scalar(0.0)

                    # accumulating
                    vars(self)[var+'AnnuaTot'] += vars(self)[var]

                    # reporting at the end of the year:
                    if currTimeStep.endYear == True: 
                        self.netcdfObj.data2NetCDF(str(self.outNCDir)+"/"+ \
                                         str(var)+"_annuaTot.nc",\
                                         var,\
                          pcr2numpy(self.__getattribute__(var+'AnnuaTot'),\
                           vos.MV),timeStamp,currTimeStep.annuaIdx-1)
            # -average
            if self.outAnnuaAvgNC[0] != "None":
                for var in self.outAnnuaAvgNC:
                    # only if a accumulator variable has not been defined: 
                    if var not in self.outAnnuaTotNC: 
                        # introduce accumulator at the beginning of simulation or
                        #     reset accumulator at the beginning of the year
                        if currTimeStep.timeStepPCR == 1 or \
                           currTimeStep.doy == 1:\
                           vars(self)[var+'AnnuaTot'] = pcr.scalar(0.0)
                        # accumulating
                        vars(self)[var+'AnnuaTot'] += vars(self)[var]
                    #
                    # calculating average & reporting at the end of the year:
                    if currTimeStep.endYear == True:
                        vars(self)[var+'AnnuaAvg'] = vars(self)[var+'AnnuaTot']/\
                                                     currTimeStep.doy  
                        self.netcdfObj.data2NetCDF(str(self.outNCDir)+"/"+ \
                                         str(var)+"_annuaAvg.nc",\
                                         var,\
                          pcr2numpy(self.__getattribute__(var+'AnnuaAvg'),\
                           vos.MV),timeStamp,currTimeStep.annuaIdx-1)
            #
            # -last day of the year
            if self.outAnnuaEndNC[0] != "None":
                for var in self.outAnnuaEndNC:
                    # reporting at the end of the year:
                    if currTimeStep.endYear == True: 
                        self.netcdfObj.data2NetCDF(str(self.outNCDir)+"/"+ \
                                         str(var)+"_annuaEnd.nc",\
                                         var,\
                          pcr2numpy(self.__getattribute__(var),vos.MV),\
                                         timeStamp,currTimeStep.annuaIdx-1)

