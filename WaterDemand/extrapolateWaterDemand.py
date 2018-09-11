#!/usr/bin/env python

# extrapolateWaterDemand.py
# 

#-modules and packages

import os, sys
import zlib,zipfile

sys.path.insert(0,'/home/beek0120/netData/pylib')

import numpy as np
import pcraster as pcr
from types import NoneType
from pcraster.framework import generateNameT
from spatialDataSet2PCR import spatialAttributes, spatialDataSet

def main():
	
	#-INITIALIZATION
	#-set output path
	outputPath= '/storagetemp/rens/SSP2/WaterDemand'
	SSPNames= ['SSP2']
	#-clone maps
	globalClone5minFileName= '/data/hydroworld/PCRGLOBWB20/input5min/global/global_clone5min.map'
	globalClone30minFileName= '/data/hydroworld/PCRGLOBWB20/input30min/global/Global_CloneMap_30min.map'
	cellAreaFileName= '/data/hydroworld/PCRGLOBWB20/input5min/routing/cellsize05min.correct.map'
	#-years of interest
	indexYear= 2010
	projectionYear= 2050
	scenarioYears= range(2010, 2101)
	#-population
	populationZipFile= '/home/beek0120/netData/GlobalDataSets/Hyde/Version_3.2_Beta2016/zip/%04dAD_pop.zip'
	populationFileRoot= 'popc_%04dAD.asc'
	populationFileRootSSP= '/home/beek0120/netData/GlobalDataSets/Hyde/SSP/%s/zip/%04dAD_pop.zip'
	#-water demand
	waterDemandTypes= ['GrossDemand', 'NettoDemand']
	sectors= ['domestic', 'industry']
	waterDemandFileRoot= '/home/sutan101/data/data_from_yoshi/GLOWASIS_water_demand/05min/remapbil/%s_water_demand_5min_meter_per_day_date_fixed.nc'
	months= range(1,13)
	startBand= 600
	#-set input for water consumption
	# water consumption is used under the assumption that return flows do not change
	waterConsumptionFileRoot= '/home/beek0120/netData/PBL/GLO/WaterDemand/consumption_m3_day_%04d.asc'
	#-IMAGE regions
	regionsFileName= '/home/beek0120/netData/PBL/BEO/data/Image_Regions/Image_Regions.map'
	#-parameters
	dummyVariableName= 'dummy'
	cellID30minFileName= 'cellid30min.map'

	#-START
	#-echo
	print ' * processing water demand'.upper()
	#-create output path
	if not os.path.isdir(outputPath):
		os.makedirs(outputPath)
	#-create IDs for processing
	commandStr= 'pcrcalc --clone %s "%s= uniqueid(boolean(1))"' %\
		(globalClone30minFileName, cellID30minFileName)
	os.system(commandStr)
	#-set clone at 5 minutes
	cloneAttributes= spatialAttributes(globalClone5minFileName)
	try:
		os.remove('temp_clone.map')
	except:
		pass
	command= 'mapattr -s -R %d -C %d -B -x %f -y %f -l %f -P yb2t temp_clone.map' %\
		(cloneAttributes.numberRows, cloneAttributes.numberCols, cloneAttributes.xLL, cloneAttributes.yUR, cloneAttributes.xResolution)
	os.system(command)
	pcr.setclone('temp_clone.map')
	try:
		os.remove('temp_clone.map')
	except:
		pass
	#-read in cell area
	cellArea= getattr(spatialDataSet(dummyVariableName,\
		cellAreaFileName,'FLOAT32', 'SCALAR',\
		cloneAttributes.xLL, cloneAttributes.xUR, cloneAttributes.yLL, cloneAttributes.yUR,\
		cloneAttributes.xResolution, cloneAttributes.yResolution,\
		pixels= cloneAttributes.numberCols, lines= cloneAttributes.numberRows), dummyVariableName)
	#-read in cell IDs
	cellIDs= getattr(spatialDataSet(dummyVariableName,\
		cellID30minFileName,'INT32', 'NOMINAL',\
		cloneAttributes.xLL, cloneAttributes.xUR, cloneAttributes.yLL, cloneAttributes.yUR,\
		cloneAttributes.xResolution, cloneAttributes.yResolution,\
		pixels= cloneAttributes.numberCols, lines= cloneAttributes.numberRows), dummyVariableName)
	os.remove(cellID30minFileName)
	#-read in IMAGE regions
	regionIDs= getattr(spatialDataSet(dummyVariableName,\
		regionsFileName,'INT32', 'NOMINAL',\
		cloneAttributes.xLL, cloneAttributes.xUR, cloneAttributes.yLL, cloneAttributes.yUR,\
		cloneAttributes.xResolution, cloneAttributes.yResolution,\
		pixels= cloneAttributes.numberCols, lines= cloneAttributes.numberRows), dummyVariableName)
	#-extract the water demand and population first at 5 arc minutes, then sum over 0.5 degree cells
	#-get population
	popZipFile= zipfile.ZipFile(populationZipFile % indexYear)
	popZipFile.extract(populationFileRoot % indexYear)
	popZipFile.close()
	totalPopulation= getattr(spatialDataSet(dummyVariableName,\
		populationFileRoot % indexYear,'FLOAT32', 'SCALAR',\
		cloneAttributes.xLL, cloneAttributes.xUR, cloneAttributes.yLL, cloneAttributes.yUR,\
		cloneAttributes.xResolution, cloneAttributes.yResolution,\
		pixels= cloneAttributes.numberCols, lines= cloneAttributes.numberRows), dummyVariableName)
	os.remove(populationFileRoot % indexYear)
	totalPopulationAggr= pcr.areatotal(totalPopulation, cellIDs)
	#-index water consumption as proxy for demand
	waterConsumptionIndexYear= getattr(spatialDataSet(dummyVariableName,\
		waterConsumptionFileRoot % indexYear,'FLOAT32', 'SCALAR',\
		cloneAttributes.xLL, cloneAttributes.xUR, cloneAttributes.yLL, cloneAttributes.yUR,\
		cloneAttributes.xResolution, cloneAttributes.yResolution,\
		pixels= cloneAttributes.numberCols, lines= cloneAttributes.numberRows), dummyVariableName)
	waterConsumptionProjectionYear= getattr(spatialDataSet(dummyVariableName,\
		waterConsumptionFileRoot % projectionYear,'FLOAT32', 'SCALAR',\
		cloneAttributes.xLL, cloneAttributes.xUR, cloneAttributes.yLL, cloneAttributes.yUR,\
		cloneAttributes.xResolution, cloneAttributes.yResolution,\
		pixels= cloneAttributes.numberCols, lines= cloneAttributes.numberRows), dummyVariableName)
	waterConsumptionIndex= (waterConsumptionProjectionYear/waterConsumptionIndexYear-1)/(projectionYear-indexYear)
	waterConsumptionIndex= pcr.cover(waterConsumptionIndex, pcr.areaaverage(waterConsumptionIndex,regionIDs), 0.0)
	pcr.report(waterConsumptionIndex, os.path.join(outputPath, 'rate_of_change.map'))
	#-read in water demand
	for sector in sectors:
		print ' - %s' % sector
		totalWaterDemand= {}
		monthlyWaterDemand= {}
		aggregatedWaterDemandPerCapita= {}
		for waterDemandType in waterDemandTypes:
			print '   %s' % waterDemandType
			#-initialize values
			totalWaterDemand[waterDemandType]= pcr.scalar(0)
			monthlyWaterDemand[waterDemandType]= {}
			#-read in values
			ncDataSet= 'NETCDF:"%s":%s%s' %\
				(waterDemandFileRoot % sector, sector, waterDemandType)
			for month in months:
				band= startBand+month
				monthlyWaterDemand[waterDemandType][month]= cellArea*getattr(spatialDataSet(dummyVariableName,\
					ncDataSet,'FLOAT32', 'SCALAR',\
					cloneAttributes.xLL, cloneAttributes.xUR, cloneAttributes.yLL, cloneAttributes.yUR,\
					cloneAttributes.xResolution, cloneAttributes.yResolution,\
					pixels= cloneAttributes.numberCols, lines= cloneAttributes.numberRows, band= band), dummyVariableName)
				totalWaterDemand[waterDemandType]+= monthlyWaterDemand[waterDemandType][month]
			#-standardize by the total
			for month in months:
				monthlyWaterDemand[waterDemandType][month]/= totalWaterDemand[waterDemandType]
				monthlyWaterDemand[waterDemandType][month]= pcr.cover(monthlyWaterDemand[waterDemandType][month], 0)
			#-get aggregated water demand and percentiles
			aggregatedWaterDemandPerCapita[waterDemandType]= pcr.areatotal(totalWaterDemand[waterDemandType],cellIDs)/totalPopulationAggr
			rankOrder= pcr.areaorder(pcr.ifthen(aggregatedWaterDemandPerCapita[waterDemandType] > 0, aggregatedWaterDemandPerCapita[waterDemandType]), regionIDs)/\
				pcr.areatotal(pcr.ifthen(aggregatedWaterDemandPerCapita[waterDemandType] > 0, pcr.scalar(1)), regionIDs)
			pLow=  pcr.areaminimum(pcr.ifthen(rankOrder >= 0.10, aggregatedWaterDemandPerCapita[waterDemandType]), regionIDs)
			pHigh= pcr.areamaximum(pcr.ifthen(rankOrder <= 0.90, aggregatedWaterDemandPerCapita[waterDemandType]), regionIDs)
			aggregatedWaterDemandPerCapita[waterDemandType]= pcr.min(pHigh, pcr.max(pLow, aggregatedWaterDemandPerCapita[waterDemandType]))
			aggregatedWaterDemandPerCapita[waterDemandType]= pcr.cover(pcr.cover(aggregatedWaterDemandPerCapita[waterDemandType], pLow), 0.0)
		#-all water demand processed, obtain return flow
		aggregatedWaterDemandPerCapita['returnflow']= pcr.max(0.0,\
			aggregatedWaterDemandPerCapita['GrossDemand']-aggregatedWaterDemandPerCapita['NettoDemand'])
		for key in totalWaterDemand.keys():
			pcr.report(aggregatedWaterDemandPerCapita[key], os.path.join(outputPath, '%s_per_capita.map' % key.lower()))
		#-echo 
		print ' * all data on water demand processed'
		#-iterate over scenarios and years
		for SSPName in SSPNames:
			print ' * processing %s' % SSPName
			for scenarioYear in scenarioYears:
				#-get population
				if os.path.isfile(populationFileRootSSP % (SSPName, scenarioYear)):
					#-extract data
					popZipFile= zipfile.ZipFile(populationFileRootSSP % (SSPName, scenarioYear))
					popZipFile.extract(populationFileRoot % scenarioYear)
					popZipFile.close()
					totalPopulation= getattr(spatialDataSet(dummyVariableName,\
						populationFileRoot % scenarioYear,'FLOAT32', 'SCALAR',\
						cloneAttributes.xLL, cloneAttributes.xUR, cloneAttributes.yLL, cloneAttributes.yUR,\
						cloneAttributes.xResolution, cloneAttributes.yResolution,\
						pixels= cloneAttributes.numberCols, lines= cloneAttributes.numberRows), dummyVariableName)
					os.remove(populationFileRoot % scenarioYear)
					#-update netto demand
					key= 'NettoDemand'
					pLow=  pcr.areaminimum(aggregatedWaterDemandPerCapita[key], regionIDs)
					pHigh= pcr.areamaximum(aggregatedWaterDemandPerCapita[key], regionIDs)
					nettoWaterDemand= pcr.min(pHigh, pcr.max(pLow,\
						(1+waterConsumptionIndex*(scenarioYear-indexYear))*aggregatedWaterDemandPerCapita[key]))
					nettoWaterDemand*= totalPopulation
					#-update gross demand
					key= 'returnflow'
					grossWaterDemand= nettoWaterDemand+aggregatedWaterDemandPerCapita[key]*totalPopulation
					print '   %s water demand for the year %04d amounts to %.1f km3 gross and %.1f km3 net per year' %\
						(sector, scenarioYear,365.25/12*1e-9*pcr.cellvalue(pcr.maptotal(grossWaterDemand),1)[0],\
							365.25/12*1e-9*pcr.cellvalue(pcr.maptotal(nettoWaterDemand),1)[0])
					pcr.report(nettoWaterDemand,os.path.join(outputPath, generateNameT('nettodem',scenarioYears.index(scenarioYear)+1)))
					pcr.report(grossWaterDemand,os.path.join(outputPath, generateNameT('grossdem',scenarioYears.index(scenarioYear)+1)))
			#-all years processed
			
	
					
	sys.exit()
	
if __name__ == '__main__':
	main()
	sys.exit('all done')
