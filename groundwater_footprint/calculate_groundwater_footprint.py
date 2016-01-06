#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import pcraster as pcr

import virtualOS as vos

# set clone
clone_map = "/data/hydroworld/PCRGLOBWB20/input5min/routing/lddsound_05min.map"
pcr.setclone(clone_map)

# class map used:
class_map =  pcr.readmap("/home/sutan101/data/aqueduct_gis_layers/aqueduct_shp_from_marta/Aqueduct_States.map")
 
# cell_area (unit: m2)
cell_area = pcr.readmap("/data/hydroworld/PCRGLOBWB20/input5min/routing/cellsize05min.correct.map") 

# fraction for groundwater recharge to be reserved to meet the environmental flow
fraction_reserved_recharge = vos.readPCRmapClone("/nfsarchive/edwin-emergency-backup-DO-NOT-DELETE/rapid/edwin/05min_runs_results/2015_04_27/non_natural_2015_04_27/global/analysis/reservedrecharge/fraction_reserved_recharge10.map", clone_map, "/scratch/edwin/tmp/tmp/")

# areal_groundwater_abstraction (unit: m/year)
groundwater_abstraction = pcr.readmap("/nfsarchive/edwin-emergency-backup-DO-NOT-DELETE/rapid/edwin/05min_runs_results/2015_04_27/non_natural_2015_04_27/global/analysis/avg_values_1990_to_2010/totalGroundwaterAbstraction_annuaTot_output_1990to2010.map")
areal_groundwater_abstraction = pcr.areatotal(groundwater_abstraction * cell_area, class_map)/pcr.areatotal(cell_area, class_map)

# areal groundwater recharge (unit: m/year)
# cdo command: cdo setunit,m.year-1 -timavg -yearsum -selyear,1990/2010 ../../netcdf/gwRecharge_monthTot_output.nc gwRecharge_annuaTot_output_1990to2010.nc
groundwater_recharge = pcr.readmap("/nfsarchive/edwin-emergency-backup-DO-NOT-DELETE/rapid/edwin/05min_runs_results/2015_04_27/non_natural_2015_04_27/global/analysis/avg_values_1990_to_2010/gwRecharge_annuaTot_output_1990to2010.map") 
# - ignore negative groundwater recharge (due to capillary rise)
areal_groundwater_recharge = pcr.max(0.0, groundwater_recharge)
areal_groundwater_recharge = pcr.areatotal(groundwater_recharge * cell_area, class_map)/pcr.areatotal(cell_area, class_map)

# areal groundwater contribution to meet enviromental flow (unit: m/year)
groundwater_contribution_to_environmental_flow       = fraction_reserved_recharge * groundwater_recharge
areal_groundwater_contribution_to_environmental_flow = pcr.areatotal(groundwater_contribution_to_environmental_flow * cell_area, class_map)/pcr.areatotal(cell_area, class_map) 

# groundwater_foot_print_map
groundwater_foot_print_map = areal_groundwater_abstraction/(areal_groundwater_recharge - areal_groundwater_contribution_to_environmental_flow)
pcr.aguila(groundwater_foot_print_map)
pcr.report(groundwater_foot_print_map, "groundwater_foot_print_map.test.map")
