#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import pcraster as pcr

import virtualOS as vos

# output directory and file_name
output_directory = "/scratch/edwin/tmp_test/"
file_name        = "test.map"
try:
	os.makedirs(output_directory)
except:
	pass

# making temporary directory:
tmp_directory = output_directory + "/tmp/"
try:
	os.makedirs(tmp_directory)
except:
	pass

# set clone
clone_map = "/data/hydroworld/PCRGLOBWB20/input5min/routing/lddsound_05min.map"
pcr.setclone(clone_map)

# landmask map
landmask = pcr.defined(pcr.readmap(clone_map))

# class map used:
class_map_file_name = "/home/sutan101/data/aqueduct_gis_layers/aqueduct_shp_from_marta/Aqueduct_States.map"
#~ class_map_file_name = "/home/sutan101/data/aqueduct_gis_layers/aqueduct_shp_from_marta/Aqueduct_GDBD.map"
#~ class_map_file_name = "/home/sutan101/data/processing_whymap/version_19september2014/major_aquifer_30min.extended.map"
#~ class_map_file_name = "/home/sutan101/data/processing_whymap/version_19september2014/major_aquifer_30min.map"
class_map    = vos.readPCRmapClone(class_map_file_name, clone_map, tmp_directory, None, False, None, True, False)
class_map    = pcr.ifthen(pcr.scalar(class_map) > 0.0, pcr.nominal(class_map)) 
#~ class_map    = pcr.nominal(pcr.uniqueid(landmask))
 
# cell_area (unit: m2)
cell_area = pcr.readmap("/data/hydroworld/PCRGLOBWB20/input5min/routing/cellsize05min.correct.map") 
segment_cell_area = pcr.areatotal(cell_area, class_map)

# extent of aquifer/sedimentary basins:
sedimentary_basin = pcr.cover(pcr.scalar(pcr.readmap("/home/sutan101/data/sed_extent/sed_extent.map")), 0.0)
cell_area = sedimentary_basin * cell_area
cell_area = pcr.ifthenelse(pcr.areatotal(cell_area, class_map) > 0.25 * segment_cell_area, cell_area, 0.0)

class_map    = pcr.ifthen(sedimentary_basin > 0, class_map)

# fraction for groundwater recharge to be reserved to meet the environmental flow
fraction_reserved_recharge = pcr.readmap("/nfsarchive/edwin-emergency-backup-DO-NOT-DELETE/rapid/edwin/05min_runs_results/2015_04_27/non_natural_2015_04_27/global/analysis/reservedrecharge/minimum_fraction_reserved_recharge10.5min.map")
# - extrapolation
fraction_reserved_recharge = pcr.cover(fraction_reserved_recharge, \
                                       pcr.windowaverage(fraction_reserved_recharge, 0.5))
fraction_reserved_recharge = pcr.cover(fraction_reserved_recharge, \
                                       pcr.windowaverage(fraction_reserved_recharge, 0.5))
fraction_reserved_recharge = pcr.cover(fraction_reserved_recharge, \
                                       pcr.windowaverage(fraction_reserved_recharge, 0.5))
fraction_reserved_recharge = pcr.cover(fraction_reserved_recharge, \
                                       pcr.windowaverage(fraction_reserved_recharge, 0.5))
fraction_reserved_recharge = pcr.cover(fraction_reserved_recharge, \
                                       pcr.windowaverage(fraction_reserved_recharge, 0.5))
fraction_reserved_recharge = pcr.cover(fraction_reserved_recharge, \
                                       pcr.windowaverage(fraction_reserved_recharge, 0.5))
fraction_reserved_recharge = pcr.cover(fraction_reserved_recharge, \
                                       pcr.windowaverage(fraction_reserved_recharge, 0.5))
fraction_reserved_recharge = pcr.cover(fraction_reserved_recharge, 0.1)
# - set minimum value to 0.00
fraction_reserved_recharge = pcr.max(0.10, fraction_reserved_recharge)
# - set maximum value to 0.90
fraction_reserved_recharge = pcr.min(0.90, fraction_reserved_recharge)

# areal_groundwater_abstraction (unit: m/year)
groundwater_abstraction = pcr.cover(pcr.readmap("/nfsarchive/edwin-emergency-backup-DO-NOT-DELETE/rapid/edwin/05min_runs_results/2015_04_27/non_natural_2015_04_27/global/analysis/avg_values_1990_to_2010/totalGroundwaterAbstraction_annuaTot_output_1990to2010.map"), 0.0)
areal_groundwater_abstraction = pcr.cover(pcr.areatotal(groundwater_abstraction * cell_area, class_map)/pcr.areatotal(cell_area, class_map), 0.0)

# areal groundwater recharge (unit: m/year)
# cdo command: cdo setunit,m.year-1 -timavg -yearsum -selyear,1990/2010 ../../netcdf/gwRecharge_monthTot_output.nc gwRecharge_annuaTot_output_1990to2010.nc
groundwater_recharge = pcr.cover(pcr.readmap("/nfsarchive/edwin-emergency-backup-DO-NOT-DELETE/rapid/edwin/05min_runs_results/2015_04_27/non_natural_2015_04_27/global/analysis/avg_values_1990_to_2010/gwRecharge_annuaTot_output_1990to2010.map"), 0.0) 
areal_groundwater_recharge = pcr.areatotal(groundwater_recharge * cell_area, class_map)/pcr.areatotal(cell_area, class_map)
# - ignore negative groundwater recharge (due to capillary rise)
areal_groundwater_recharge = pcr.max(0.0, areal_groundwater_recharge)

# areal groundwater contribution to meet enviromental flow (unit: m/year)
groundwater_contribution_to_environmental_flow       = pcr.max(0.0, fraction_reserved_recharge * groundwater_recharge)
areal_groundwater_contribution_to_environmental_flow = pcr.areatotal(groundwater_contribution_to_environmental_flow * cell_area, class_map)/pcr.areatotal(cell_area, class_map) 
areal_groundwater_contribution_to_environmental_flow = pcr.min(0.9 * areal_groundwater_recharge, areal_groundwater_contribution_to_environmental_flow)

# groundwater_foot_print_map
groundwater_foot_print_map = pcr.ifthen(landmask, \
                             areal_groundwater_abstraction/(pcr.cover(pcr.max(0.001, areal_groundwater_recharge - areal_groundwater_contribution_to_environmental_flow), 0.001)))
pcr.aguila(groundwater_foot_print_map)
pcr.report(groundwater_foot_print_map, "groundwater_foot_print_map.test.map")
