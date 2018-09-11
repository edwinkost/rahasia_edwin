#!/usr/bin/env python

# extrapolateWaterDemand.py
# 

#-modules and packages

import os, sys
import calendar, datetime
import zlib, zipfile, shutil, glob

sys.path.insert(0,'/home/beek0120/netData/pylib')

import numpy as np
import pcraster as pcr
from types import NoneType
from pcraster.framework import generateNameT
from spatialDataSet2PCR import spatialAttributes, spatialDataSet, setClone
import ncRecipes_fixed as ncr

def extractFileFromZip(zipFileName, archiveName, targetName):
	zipFile= zipfile.ZipFile(zipFileName)
	zipFile.extract(archiveName)
	shutil.move(archiveName, targetName)
	zipFile.close()

def extractYearsFromFiles(searchStr, splitStr):
	'''
	finds in a directory the corresponding years
	'''
	#-returns the years from a global search string 
	availableYears= glob.glob(searchStr.replace(splitStr, '*'))
	nameParts= searchStr.split(splitStr)
	
	for iCnt in xrange(len(availableYears)):
		for namePart in nameParts:
			availableYears[iCnt]= availableYears[iCnt].replace(namePart,'')
		availableYears[iCnt]= int(availableYears[iCnt])
	availableYears.sort()

	return availableYears

def matchYearsFromLists(availableYears, years):
	'''
	matches all years with the entries from availableYears
	and returns a dictionary
	'''

	matchedYears= dict(((availableYears[iCnt], availableYears[iCnt+1]), []) \
		for iCnt in xrange(len(availableYears)-1))
	
	for year in years:
		for boundingYears in matchedYears.keys():
			if year >= boundingYears[0] and year < boundingYears[1]:
				matchedYears[boundingYears].append(year)
	
	removeList= []
	for key, value in matchedYears.iteritems():
		if len(value) == 0:
			removeList.append(key)
	
	for key in removeList:
		del matchedYears[key]
	
	return matchedYears

################################################################################

def main():
	
	#-INITIALIZATION
	#-missing value
	MV= -999.9
	#-set output path
	SSPNames= ['SSP1', 'SSP2', 'SSP3']
	SSPNames= ['SSP5']
	#-clone maps
	globalClone5minFileName= '/data/hydroworld/PCRGLOBWB20/input5min/global/global_clone5min.map'
	globalClone30minFileName= '/data/hydroworld/PCRGLOBWB20/input30min/global/Global_CloneMap_30min.map'
	cellAreaFileName= '/data/hydroworld/PCRGLOBWB20/input5min/routing/cellsize05min.correct.map'
	#-years of interest
	indexYear= 2010
	projectionYear= 2050
	scenarioYears= range(2010, 2100)
	#-population
	populationZipFile= '/home/beek0120/netData/GlobalDataSets/Hyde/Version_3.2_Beta2016/zip/%04dAD_pop.zip'
	populationFileRoot= 'popc_%04dAD.asc'
	populationFileRootSSP= '/home/beek0120/netData/GlobalDataSets/Hyde/SSP/%s/zip/%04dAD_pop.zip'
	#-water demand and consumption per sector
	# water consumption is used under the assumption that return flows do not change	
	inputPath= '/home/beek0120/netData/PBL/GLO/WaterDemand/%s'
	waterDemandTypes= ['GrossDemand', 'NettoDemand']
	sectors= {'domestic': 'Muni_consumption_m3_day_%04d.asc', 'industry': 'Ind_consumption_m3_day_%04d.asc'}
	waterDemandFileRoot= '/home/sutan101/data/data_from_yoshi/GLOWASIS_water_demand/05min/remapbil/%s_water_demand_5min_meter_per_day_date_fixed.nc'
	months= range(1,13)
	startBand= 600
	#-IMAGE regions
	regionsFileName= '/home/beek0120/netData/PBL/BEO/data/Image_Regions/Image_Regions.map'
	#-parameters
	dummyVariableName= 'dummy'
	cellID30minFileName= 'cellid30min.map'

	#-netCDF settings	
	ncFileRoot= 'water_demand_%s_%s_%s_%04d-%04d_5min.nc'
	ncDynVarName= 'time'
	ncVarUnit= 'm_per_day'
	ncAltVarName= 'fracVegCover'
	ncAttributes= {}
	ncAttributes['title']= 'Vegetation parameterization for PCR-GLOBWB'
	ncAttributes['description']= 'Fraction urban area'
	ncAttributes['institution']= 'Dept. Physical Geography, Utrecht University.'
	ncAttributes['source']= 'Based on the HYDE 3.2 dataset.'
	ncAttributes['references']= 'For documentation, see Van Beek et al. (WRR, 2011, doi:10.1029/2010WR009791)'
	ncAttributes['disclaimer']= 'Great care was exerted to prepare these data.\
 Notwithstanding, use of the model and/or its outcome is the sole responsibility of the user.'
	ncAttributes['history']= 'Created on %s.' % (datetime.datetime.now()) 	

	#-START
	#-echo
	print ' * processing water demand'.upper()
	#-create IDs for processing
	commandStr= 'pcrcalc --clone %s "%s= uniqueid(boolean(1))"' %\
		(globalClone30minFileName, cellID30minFileName)
	os.system(commandStr)
	#-set clone at 5 minutes
	cloneAttributes= spatialAttributes(globalClone5minFileName)
	setClone(cloneAttributes)
	#-return latitudes and longitudes
	latitudes=  cloneAttributes.yUR-(np.arange(cloneAttributes.numberRows)+0.5)*cloneAttributes.yResolution
	longitudes= cloneAttributes.xLL+(np.arange(cloneAttributes.numberCols)+0.5)*cloneAttributes.xResolution
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

	#-process HYDE dataset: population for index and projection year
	#-extract the water demand and population first at 5 arc minutes, then sum over 0.5 degree cells
	extractFileFromZip(populationZipFile % indexYear, populationFileRoot % indexYear, populationFileRoot % indexYear)
	totalPopulation= getattr(spatialDataSet(dummyVariableName,\
		populationFileRoot % indexYear,'FLOAT32', 'SCALAR',\
		cloneAttributes.xLL, cloneAttributes.xUR, cloneAttributes.yLL, cloneAttributes.yUR,\
		cloneAttributes.xResolution, cloneAttributes.yResolution,\
		pixels= cloneAttributes.numberCols, lines= cloneAttributes.numberRows), dummyVariableName)
	os.remove(populationFileRoot % indexYear)
	totalPopulationAggr= pcr.areatotal(totalPopulation, cellIDs)
	referenceTotalPopulation= totalPopulation
	#-create output path
	for SSPName in SSPNames:
		outputPath= '/storagetemp/rens/%s/WaterDemand' % SSPName
		if not os.path.isdir(outputPath):
			os.makedirs(outputPath)
		#-read in water demand
		for sector, waterConsumptionFileRoot in sectors.iteritems():
			print ' * obtaining consumption per capita for %s under %s' % (sector, SSPName)
			#-index water consumption as proxy for demand
			waterConsumptionIndexYear= getattr(spatialDataSet(dummyVariableName,\
				os.path.join(inputPath % SSPName, waterConsumptionFileRoot % indexYear),\
				'FLOAT32', 'SCALAR',\
				cloneAttributes.xLL, cloneAttributes.xUR, cloneAttributes.yLL, cloneAttributes.yUR,\
				cloneAttributes.xResolution, cloneAttributes.yResolution,\
				pixels= cloneAttributes.numberCols, lines= cloneAttributes.numberRows), dummyVariableName)
			waterConsumptionProjectionYear= getattr(spatialDataSet(dummyVariableName,\
				os.path.join(inputPath % SSPName, waterConsumptionFileRoot % projectionYear),\
				'FLOAT32', 'SCALAR',\
				cloneAttributes.xLL, cloneAttributes.xUR, cloneAttributes.yLL, cloneAttributes.yUR,\
				cloneAttributes.xResolution, cloneAttributes.yResolution,\
				pixels= cloneAttributes.numberCols, lines= cloneAttributes.numberRows), dummyVariableName)
			waterConsumptionIndex= (waterConsumptionProjectionYear/waterConsumptionIndexYear-1)/(projectionYear-indexYear)
			waterConsumptionIndex= pcr.cover(waterConsumptionIndex, pcr.areaaverage(waterConsumptionIndex,regionIDs), 0.0)
			pcr.report(waterConsumptionIndex, os.path.join(outputPath, 'rate_of_change_%s.map' % sector))
			#-define total water demand and read in values
			totalWaterDemand= {}
			monthlyWaterDemand= {}
			aggregatedWaterDemandPerCapita= {}
			for waterDemandType in waterDemandTypes:
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
				#-get aggregated water demand and percentiles in m3 per year
				aggregatedWaterDemandPerCapita[waterDemandType]= pcr.areatotal(totalWaterDemand[waterDemandType],cellIDs)/totalPopulationAggr
				rankOrder= pcr.areaorder(pcr.ifthen(aggregatedWaterDemandPerCapita[waterDemandType] > 0, aggregatedWaterDemandPerCapita[waterDemandType]), regionIDs)/\
					pcr.areatotal(pcr.ifthen(aggregatedWaterDemandPerCapita[waterDemandType] > 0, pcr.scalar(1)), regionIDs)
				pLow=  pcr.areaminimum(pcr.ifthen(rankOrder >= 0.05, aggregatedWaterDemandPerCapita[waterDemandType]), regionIDs)
				pHigh= pcr.areamaximum(pcr.ifthen(rankOrder <= 0.95, aggregatedWaterDemandPerCapita[waterDemandType]), regionIDs)
				aggregatedWaterDemandPerCapita[waterDemandType]= pcr.min(pHigh, pcr.max(pLow, aggregatedWaterDemandPerCapita[waterDemandType]))
				aggregatedWaterDemandPerCapita[waterDemandType]= pcr.cover(pcr.cover(aggregatedWaterDemandPerCapita[waterDemandType], pLow), 0.0)
			#-all water demand processed, obtain return flow
			aggregatedWaterDemandPerCapita['returnflow']= pcr.max(0.0,\
				aggregatedWaterDemandPerCapita['GrossDemand']-aggregatedWaterDemandPerCapita['NettoDemand'])
			for key in totalWaterDemand.keys():
				pcr.report(aggregatedWaterDemandPerCapita[key], os.path.join(outputPath, '%s_%s_per_capita.map' % (sector, key.lower())))
			#-echo 
			print ' * all data on water demand processed'
			print '   %s water demand for the year %04d amounts to %.1f km3 gross and %.1f km3 net per year\n' %\
				(sector, indexYear, 365.25/12*1e-9*pcr.cellvalue(pcr.maptotal(totalWaterDemand['GrossDemand']),1)[0],\
					365.25/12*1e-9*pcr.cellvalue(pcr.maptotal(totalWaterDemand['NettoDemand']),1)[0])

			#-extract years from file names and match years
			tstPath, tstFile= os.path.split(populationFileRootSSP)
			searchStr= os.path.join(tstPath % SSPName,tstFile)
			availableYears= extractYearsFromFiles(searchStr, '%04d')
			matchedYears= matchYearsFromLists(availableYears, scenarioYears)
			#-initialize netCDF files for output
			for waterDemandType in waterDemandTypes:
				ncVarName= '%s%s' % (sector, waterDemandType)
				ncFileName= os.path.join(outputPath, ncFileRoot %\
					(sector, waterDemandType, SSPName, scenarioYears[0], scenarioYears[-1]))
				ncr.createNetCDF(ncFileName,longitudes, latitudes,\
					'lon', 'lat', ncDynVarName, ncVarName, ncVarUnit, MV, ncAttributes)
				print '   * netCDF file %s initialized *' % ncFileName
			#-process matched years
			for boundingYears, sampledYears in matchedYears.iteritems():
				extractFileFromZip(populationFileRootSSP %  (SSPName, boundingYears[0]),\
					populationFileRoot % boundingYears[0], populationFileRoot % boundingYears[0])
				intercept= getattr(spatialDataSet(dummyVariableName,\
						populationFileRoot % boundingYears[0],'FLOAT32', 'SCALAR',\
						cloneAttributes.xLL, cloneAttributes.xUR, cloneAttributes.yLL, cloneAttributes.yUR,\
						cloneAttributes.xResolution, cloneAttributes.yResolution,\
						pixels= cloneAttributes.numberCols, lines= cloneAttributes.numberRows), dummyVariableName)
				os.remove(populationFileRoot % boundingYears[0])
				#-process sample years
				#-several years, interpolate
				#-get slope from bounding years
				extractFileFromZip(populationFileRootSSP %  (SSPName, boundingYears[1]),\
					populationFileRoot % boundingYears[1], populationFileRoot % boundingYears[1])
				slope= getattr(spatialDataSet(dummyVariableName,\
						populationFileRoot % boundingYears[1],'FLOAT32', 'SCALAR',\
						cloneAttributes.xLL, cloneAttributes.xUR, cloneAttributes.yLL, cloneAttributes.yUR,\
						cloneAttributes.xResolution, cloneAttributes.yResolution,\
						pixels= cloneAttributes.numberCols, lines= cloneAttributes.numberRows), dummyVariableName)
				slope-= intercept
				slope/= (boundingYears[1]-boundingYears[0])
				os.remove(populationFileRoot % boundingYears[1])
				for year in sampledYears:
					print ' - %04d' % year,
					totalPopulation= intercept+slope*(year-boundingYears[0])
					#-update netto demand
					key= 'NettoDemand'
					pLow=  pcr.areaminimum(aggregatedWaterDemandPerCapita[key], regionIDs)
					pHigh= pcr.areamaximum(aggregatedWaterDemandPerCapita[key], regionIDs)
					nettoWaterDemand= pcr.min(pHigh, pcr.max(pLow,\
						(1+waterConsumptionIndex*(year-indexYear))*aggregatedWaterDemandPerCapita[key]))
					nettoWaterDemand*= totalPopulation
					#-update gross demand
					key= 'returnflow'
					grossWaterDemand= nettoWaterDemand+aggregatedWaterDemandPerCapita[key]*totalPopulation					
					#-report
					print '   total population in billions for current year %04d and reference: %5.3f %5.3f' %\
						(year, 1e-9*pcr.cellvalue(pcr.maptotal(totalPopulation),1)[0],\
							1e-9*pcr.cellvalue(pcr.maptotal(referenceTotalPopulation),1)[0])
					print'   and minimum and maximum between them: %d, %d' %\
						(pcr.cellvalue(pcr.mapminimum(totalPopulation-referenceTotalPopulation),1)[0],\
							pcr.cellvalue(pcr.mapmaximum(totalPopulation-referenceTotalPopulation),1)[0])
					print '   %s water demand for the year %04d amounts to %.1f km3 gross and %.1f km3 net per year\n' %\
						(sector, year,365.25/12*1e-9*pcr.cellvalue(pcr.maptotal(grossWaterDemand),1)[0],\
							365.25/12*1e-9*pcr.cellvalue(pcr.maptotal(nettoWaterDemand),1)[0])
					#-iterate over the months to obtain the the total; divide this by the cell area to obtain it in m/day
					print '   writing monthly values',
					for waterDemandType in waterDemandTypes:
						print waterDemandType,
						ncVarName= '%s%s' % (sector, waterDemandType)
						ncFileName= os.path.join(outputPath, ncFileRoot %\
							(sector, waterDemandType, SSPName, scenarioYears[0], scenarioYears[-1]))
						if waterDemandType == 'GrossDemand':
							valueField= grossWaterDemand/cellArea
						else:
							valueField= nettoWaterDemand/cellArea
						for month in months:
							posCnt= scenarioYears.index(year)*12+months.index(month)
							date= datetime.datetime(year, month, 1)
							ncr.writeField(ncFileName,\
								pcr.pcr2numpy(monthlyWaterDemand[waterDemandType][month]*valueField, MV),\
								ncVarName, date, posCnt, ncDynVarName, MV)
					print
					#-current water demand processed
				#-current year processed
	
if __name__ == '__main__':
	main()
	sys.exit('all done')
