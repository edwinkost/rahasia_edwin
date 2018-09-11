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
from zonalStatistics import zonal_statistics_pcr
import ncRecipes_fixed as ncr

################################################################################

def main():
	
	#-INITIALIZATION
	#-missing value
	MV= -999.9
	#-set output path
	scenarioNames= ['Historical', 'SSP1', 'SSP2', 'SSP3']
	
	#-clone map
	globalCloneFileName= '/data/hydroworld/PCRGLOBWB20/input30min/global/Global_CloneMap_30min.map'
	
	cellAreaFileName= '/data/hydroworld/PCRGLOBWB20/input30min/routing/cellarea30min.map'
	#-information on pumping capacity
	fpuCodeFileName= '/home/beek0120/netData/PBL/GLO/WaterDemand/design_pumping_capacity/fpu_code.map'
	pumpingCapacityTxtFileName= '/home/beek0120/netData/PBL/GLO/WaterDemand/design_pumping_capacity/pumping_capacity_1960_to_2015.csv'
	indexYears= {\
		1998: 39,\
		1999: 40,\
		2000: 41,\
		2001: 42,\
		2002: 43}
	withdrawalTypes= ['domestic', 'industry', 'irrigation', 'total']
	sectors= withdrawalTypes[:3]
	withdrawalFileRoots= {\
		'domestic': '/storagetemp/rens/abstraction_data/domesticWaterWithdrawal_annuaTot_output_%04d-12-31_to_%04d-12-31.nc',\
		'industry': '/storagetemp/rens/abstraction_data/industryWaterWithdrawal_annuaTot_output_%04d-12-31_to_%04d-12-31.nc',\
		'irrigation': '/storagetemp/rens/abstraction_data/irrPaddyWaterWithdrawal_annuaTot_output_%04d-12-31_to_%04d-12-31.nc'}
	totalAbstractionFileRoot= '/storagetemp/rens/abstraction_data/totalAbstraction_annuaTot_output_%04d-12-31_to_%04d-12-31.nc'
	#-source files organized per sector and tuple of files belonging to the index- and scenario years
	patchScenario= 'Historical'
	patchYear= 2010
	patchLengthYears= 10
	scenarioYears= {\
		'Historical': range(1970,2011),\
		'SSP1': range(2011,2100),\
		'SSP2': range(2011,2100),\
		'SSP3': range(2011,2100)}
	sourceFiles= {\
		'Historical': {\
			'domestic':   ('/home/sutan101/data/data_from_yoshi/GLOWASIS_water_demand/05min/remapbil/domestic_water_demand_5min_meter_per_day_date_fixed.nc',\
				'/home/sutan101/data/data_from_yoshi/GLOWASIS_water_demand/05min/remapbil/domestic_water_demand_5min_meter_per_day_date_fixed.nc'),\
			'industry':   ('/home/sutan101/data/data_from_yoshi/GLOWASIS_water_demand/05min/remapbil/industry_water_demand_5min_meter_per_day_date_fixed.nc',\
				'/home/sutan101/data/data_from_yoshi/GLOWASIS_water_demand/05min/remapbil/industry_water_demand_5min_meter_per_day_date_fixed.nc'),\
			'irrigation': ('/storagetemp/rens/vegetationFractions/fraction_irrigated_areatotal_historical_1970-2010.nc',\
				'/storagetemp/rens/vegetationFractions/fraction_irrigated_areatotal_historical_1970-2010.nc')},\
		'SSP1': {\
			'domestic':   ('/home/sutan101/data/data_from_yoshi/GLOWASIS_water_demand/05min/remapbil/domestic_water_demand_5min_meter_per_day_date_fixed.nc',\
				'/storagetemp/rens/SSP1/WaterDemand/water_demand_domestic_GrossDemand_SSP1_2010-2099_5min.nc'),\
			'industry':   ('/home/sutan101/data/data_from_yoshi/GLOWASIS_water_demand/05min/remapbil/industry_water_demand_5min_meter_per_day_date_fixed.nc',\
				'/storagetemp/rens/SSP1/WaterDemand/water_demand_industry_GrossDemand_SSP1_2010-2099_5min.nc'),\
			'irrigation': ('/storagetemp/rens/vegetationFractions/fraction_irrigated_areatotal_historical_1970-2010.nc',\
				'/storagetemp/rens/vegetationFractions/fraction_irrigated_areatotal_SSP1_2011-2100.nc')},\
		'SSP2': {\
			'domestic':   ('/home/sutan101/data/data_from_yoshi/GLOWASIS_water_demand/05min/remapbil/domestic_water_demand_5min_meter_per_day_date_fixed.nc',\
				'/storagetemp/rens/SSP2/WaterDemand/water_demand_domestic_GrossDemand_SSP2_2010-2099_5min.nc'),\
			'industry':   ('/home/sutan101/data/data_from_yoshi/GLOWASIS_water_demand/05min/remapbil/industry_water_demand_5min_meter_per_day_date_fixed.nc',\
				'/storagetemp/rens/SSP2/WaterDemand/water_demand_industry_GrossDemand_SSP2_2010-2099_5min.nc'),\
			'irrigation': ('/storagetemp/rens/vegetationFractions/fraction_irrigated_areatotal_historical_1970-2010.nc',\
				'/storagetemp/rens/vegetationFractions/fraction_irrigated_areatotal_SSP2_2011-2100.nc')},\
		'SSP3': {\
			'domestic':   ('/home/sutan101/data/data_from_yoshi/GLOWASIS_water_demand/05min/remapbil/domestic_water_demand_5min_meter_per_day_date_fixed.nc',\
				'/storagetemp/rens/SSP3/WaterDemand/water_demand_domestic_GrossDemand_SSP3_2010-2099_5min.nc'),\
			'industry':   ('/home/sutan101/data/data_from_yoshi/GLOWASIS_water_demand/05min/remapbil/industry_water_demand_5min_meter_per_day_date_fixed.nc',\
				'/storagetemp/rens/SSP3/WaterDemand/water_demand_industry_GrossDemand_SSP3_2010-2099_5min.nc'),\
			'irrigation': ('/storagetemp/rens/vegetationFractions/fraction_irrigated_areatotal_historical_1970-2010.nc',\
				'/storagetemp/rens/vegetationFractions/fraction_irrigated_areatotal_SSP3_2011-2100.nc')}}
	sourceVariableNames= dict((scenarioName, {'domestic':   'domesticGrossDemand',\
		'industry':   'industryGrossDemand',\
		'irrigation': 'vegetation_fraction'}) for scenarioName in scenarioNames)

	#~ globalCloneFileName= '/home/beek0120/PCRGLOBWB/CloneMaps/domain_mississippi_30min.map'
	#~ scenarioNames= scenarioNames[1:]
	#~ scenarioYears= {\
		#~ 'Historical': (2000, 2009, 2010),\
		#~ 'SSP1': (2011,2050),\
		#~ 'SSP2': (2011,2050),\
		#~ 'SSP3': (2011,2050)}

	#-netCDF settings	
	ncFileRoot= 'groundwater_pumping_capacity_%s_%04d-%04d_30min.nc'
	ncDynVarName= 'time'
	ncVarName= 'regional_pumping_limit'
	ncVarUnit= 'billion_cubic_m_per_year'
	ncAttributes= {}
	ncAttributes['title']= 'Pumping capacity reconstructed on the basis of demand of water demand and irrigated area'
	ncAttributes['description']= 'Pumping capacity'
	ncAttributes['institution']= 'Dept. Physical Geography, Utrecht University.'
	ncAttributes['source']= 'Based on the HYDE 3.2 dataset.'
	ncAttributes['references']= 'For documentation, see Van Beek et al. (WRR, 2011, doi:10.1029/2010WR009791)'
	ncAttributes['disclaimer']= 'Great care was exerted to prepare these data.\
 Notwithstanding, use of the model and/or its outcome is the sole responsibility of the user.'
	ncAttributes['history']= 'Created on %s.' % (datetime.datetime.now()) 	
	
	#-parameters
	dummyVariableName= 'dummy'
	testReport= True
	
	#-START
	#-echo
	print ' * processing pumping capacity'.upper()
	#-create output path
	outputPath= '/storagetemp/rens/limit_gw_abstraction'
	if not os.path.isdir(outputPath):
		os.makedirs(outputPath)
	#-initialize value to patch scenarios
	patchValue= None
	#-set matrix option
	pcr.setglobaloption('matrixtable')
	#-set clone at 5 minutes
	cloneAttributes= spatialAttributes(globalCloneFileName)
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
	#-read in fpu code
	print ' - reading in code'
	fpuCode=  getattr(spatialDataSet(dummyVariableName,\
		fpuCodeFileName, 'INT32', 'NOMINAL',\
		cloneAttributes.xLL, cloneAttributes.xUR, cloneAttributes.yLL, cloneAttributes.yUR,\
		cloneAttributes.xResolution, cloneAttributes.yResolution,\
		pixels= cloneAttributes.numberCols, lines= cloneAttributes.numberRows), dummyVariableName)
	fpuIDs= np.unique(pcr.pcr2numpy(fpuCode,0))
	fpuIDs= fpuIDs[(fpuIDs != 0) & (fpuIDs != 999999)]
	fpuIDs= fpuIDs.tolist()
	fpuIDs.sort()
	#-obtain average of withdrawals, total abstraction and pumping capacity over the years selected
	# weight is used to obtain the input for an average year centred on the index year,
	# water depths are multiplied by area in order to obtain totals
	withdrawal= dict((withdrawalType, pcr.scalar(0)) for withdrawalType in withdrawalTypes)
	totalAbstraction= pcr.scalar(0)
	pumpingCapacity= pcr.scalar(0)
	weight= 1.0/len(indexYears)
	print ' - extracting info for:', 
	for indexYear, columnNumber in indexYears.iteritems():
		print indexYear,
		for withdrawalType, fileRoot in withdrawalFileRoots.iteritems():
			valueField= getattr(spatialDataSet(dummyVariableName,\
				fileRoot % (indexYear, indexYear),'FLOAT32', 'SCALAR',\
				cloneAttributes.xLL, cloneAttributes.xUR, cloneAttributes.yLL, cloneAttributes.yUR,\
				cloneAttributes.xResolution, cloneAttributes.yResolution,\
				pixels= cloneAttributes.numberCols, lines= cloneAttributes.numberRows), dummyVariableName)
			withdrawal[withdrawalType]+= cellArea*weight*valueField
			withdrawal['total']+= cellArea*weight*valueField
		totalAbstraction+= cellArea*weight*getattr(spatialDataSet(dummyVariableName,\
			totalAbstractionFileRoot % (indexYear, indexYear),'FLOAT32', 'SCALAR',\
			cloneAttributes.xLL, cloneAttributes.xUR, cloneAttributes.yLL, cloneAttributes.yUR,\
			cloneAttributes.xResolution, cloneAttributes.yResolution,\
			pixels= cloneAttributes.numberCols, lines= cloneAttributes.numberRows), dummyVariableName)
		pumpingCapacity+= weight*pcr.lookupscalar(pumpingCapacityTxtFileName, columnNumber, fpuCode)
	print
	#-iterate over the different parts and convert it to billion cubic m per year as used for the groundwater pumping capacity
	for withdrawalType in withdrawalTypes:
		withdrawal[withdrawalType]= pcr.areatotal(1.0e-9*withdrawal[withdrawalType], fpuCode)
	totalAbstraction= pcr.areatotal(1.0e-9*totalAbstraction, fpuCode)
	#-take maximum of total abstraction or computed total withdrawal and compute ratio
	withdrawal['total']= pcr.max(withdrawal['total'], totalAbstraction)
	withdrawal['irrigation']= pcr.max(0.0,withdrawal['total']-(withdrawal['domestic']+withdrawal['industry']))
	sectorPumpingCapacity= {}
	for withdrawalType in withdrawalFileRoots.keys():
		withdrawal[withdrawalType]/= withdrawal['total']
		sectorPumpingCapacity[withdrawalType]= pcr.cover(withdrawal[withdrawalType], 1.0/len(sectors))*pumpingCapacity
	#-intermediate report
	if testReport:
		print ' - reporting test maps'
		for withdrawalType in withdrawalFileRoots.keys():
			pcr.report(withdrawal[withdrawalType],'fraction_%s.map' % withdrawalType)
			pcr.report(sectorPumpingCapacity[withdrawalType],'pumpingcapacity_%s.map' % withdrawalType)
		pcr.report(totalAbstraction,'totalabstraction.map')
		pcr.report(fpuCode,'fpu_code.map')
		pcr.report(pumpingCapacity, 'pumping_capacity.map')
	#-initial information derived
	indexYear= int(sum(indexYears.keys())/len(indexYears))
	print ' - all initial information for index year %d derived' % indexYear
	totalPumpingCapacity= sum(zonal_statistics_pcr(pumpingCapacity, fpuCode, fpuIDs, np.mean))
	print '   total global pumping capacity amounts to %.2f billion cubic metres per year' % totalPumpingCapacity
	totalPumpingCapacity= 0.0
	for withdrawalType in withdrawalFileRoots.keys():
		totalPumpingCapacitySector= sum(zonal_statistics_pcr(sectorPumpingCapacity[withdrawalType], fpuCode, fpuIDs, np.mean))
		print '   total global pumping capacity for %15s amounts to %.2f billion cubic metres per year' % (withdrawalType, totalPumpingCapacitySector)
		totalPumpingCapacity+= totalPumpingCapacitySector
	print '   total global pumping capacity amounts to %.2f billion cubic metres per year' % totalPumpingCapacity

	#-iterate over scenarios and read the relevant information for the year of interest
	for scenarioName in scenarioNames:
		#-echo
		print ' * processing info for %s' % scenarioName
		referenceValues={}
		#-obtain reference values per sector
		for sector in sectors:
			print ' - %s' % sector
			ncInFile= sourceFiles[scenarioName][sector][0]
			sourceVariableName= sourceVariableNames[scenarioName][sector]
			ncDataSet= 'NETCDF:"%s":%s' %\
				(ncInFile, sourceVariableName)
			referenceValues[sector]= pcr.scalar(0)
			iCnt= 0
			ncDates= ncr.getNCDates(ncInFile).tolist()
			for ncDate in ncDates:
				if ncDate.year == indexYear:
					band= ncDates.index(ncDate)+1
					valueField= cellArea*getattr(spatialDataSet(dummyVariableName,\
						ncDataSet,'FLOAT32', 'SCALAR',\
						cloneAttributes.xLL, cloneAttributes.xUR, cloneAttributes.yLL, cloneAttributes.yUR,\
						cloneAttributes.xResolution, cloneAttributes.yResolution,\
						pixels= cloneAttributes.numberCols, lines= cloneAttributes.numberRows, band= band), dummyVariableName)
					referenceValues[sector]+= valueField
					iCnt+= 1
			referenceValues[sector]/= iCnt
			referenceValues[sector]= pcr.areatotal(referenceValues[sector], fpuCode)
		#-all reference values obtained
		print ' - reference values obtained'	

		#-initialize netCDF file
		ncFileName= os.path.join(outputPath, ncFileRoot %\
			(scenarioName, scenarioYears[scenarioName][0], scenarioYears[scenarioName][-1]))
		ncr.createNetCDF(ncFileName,longitudes, latitudes,\
			'lon', 'lat', ncDynVarName, ncVarName, ncVarUnit, MV, ncAttributes)
		print '   netCDF file %s initialized' % ncFileName
		#-initialize array
		groundwaterPumpingCapacityTSS= np.ones((len(fpuIDs), len(scenarioYears[scenarioName])))*MV
		#-iterate over years
		for year in scenarioYears[scenarioName]:
			#-initialize annual pumping capacity
			annualPumpingCapacity= pcr.scalar(0)
			#-obtain pumping capacity values per sector
			annualValues= {}
			for sector in sectors:
				ncInFile= sourceFiles[scenarioName][sector][1]
				sourceVariableName= sourceVariableNames[scenarioName][sector]
				ncDataSet= 'NETCDF:"%s":%s' %\
					(ncInFile, sourceVariableName)
				annualValues[sector]= pcr.scalar(0)
				iCnt= 0
				ncDates= ncr.getNCDates(ncInFile).tolist()
				for ncDate in ncDates:
					if ncDate.year == year:
						band= ncDates.index(ncDate)+1
						valueField= cellArea*getattr(spatialDataSet(dummyVariableName,\
							ncDataSet,'FLOAT32', 'SCALAR',\
							cloneAttributes.xLL, cloneAttributes.xUR, cloneAttributes.yLL, cloneAttributes.yUR,\
							cloneAttributes.xResolution, cloneAttributes.yResolution,\
							pixels= cloneAttributes.numberCols, lines= cloneAttributes.numberRows, band= band), dummyVariableName)
						annualValues[sector]+= valueField
						iCnt+= 1
				annualValues[sector]/= iCnt
				annualValues[sector]= pcr.areatotal(annualValues[sector], fpuCode)
				weight= pcr.cover(annualValues[sector]/referenceValues[sector], 1.0)
				annualPumpingCapacity+= weight*sectorPumpingCapacity[sector]
			annualPumpingCapacity= pcr.cover(annualPumpingCapacity, pumpingCapacity, 0)
			#-patch value
			if scenarioName != patchScenario and not isinstance(patchValue, NoneType):
				#-patch using the blend year
				blendRatio= min(1.0,abs(float(year-patchYear)/patchLengthYears))
				annualPumpingCapacity= blendRatio*annualPumpingCapacity+(1.0-blendRatio)*patchValue			
			#-annual pumping capacity obtained, write values to netCDF
			date= datetime.datetime(year, 1, 1)
			posCnt= scenarioYears[scenarioName].index(year)
			ncr.writeField(ncFileName,\
				pcr.pcr2numpy(annualPumpingCapacity, MV),\
				ncVarName, date, posCnt, ncDynVarName, MV)
			#-get statistics
			annualPumpingCapacityMeans= zonal_statistics_pcr(annualPumpingCapacity, fpuCode, fpuIDs, np.mean)
			groundwaterPumpingCapacityTSS[:,scenarioYears[scenarioName].index(year)]= \
				annualPumpingCapacityMeans[:]
			totalPumpingCapacity= sum(annualPumpingCapacityMeans)
			print '   for the year %04d total global pumping capacity amounts to %8.2f billion cubic metres per ' % (year, totalPumpingCapacity)
			#-current year processed
			# check on patch
			if scenarioName == patchScenario and year == patchYear:
				print '   capacity for %d set for subsequent correction' % year
				patchValue= annualPumpingCapacity

		#-all years processed
		txtFileName= ncFileName.replace('.nc', '.txt')
		np.savetxt(txtFileName, groundwaterPumpingCapacityTSS, fmt= '%.3f')
		print
	
if __name__ == '__main__':
	main()
	sys.exit('all done')

			#~ if sector != 'irrigation' and  sourceFiles[scenarioName][sector][0] != sourceFiles[scenarioName][sector][1]:
				#~ print '   patching %s' % sector
				#~ #-set up value from the reference files
				#~ indexValue= pcr.scalar(0.0)
				#~ iCnt= 0
				#~ for ncDate in ncDates:
					#~ if ncDate.year == indexYear:
						#~ band= ncDates.index(ncDate)+1
						#~ valueField= cellArea*getattr(spatialDataSet(dummyVariableName,\
							#~ ncDataSet,'FLOAT32', 'SCALAR',\
							#~ cloneAttributes.xLL, cloneAttributes.xUR, cloneAttributes.yLL, cloneAttributes.yUR,\
							#~ cloneAttributes.xResolution, cloneAttributes.yResolution,\
							#~ pixels= cloneAttributes.numberCols, lines= cloneAttributes.numberRows, band= band), dummyVariableName)
						#~ indexValue+= valueField
						#~ iCnt+= 1
				#~ indexValue/= iCnt
				#~ indexValue= pcr.areatotal(indexValue, fpuCode)
				#~ #-set up value from scenario file			
				#~ ncInFile= sourceFiles[scenarioName][sector][1]
				#~ sourceVariableName= sourceVariableNames[scenarioName][sector]
				#~ ncDataSet= 'NETCDF:"%s":%s' %\
					#~ (ncInFile, sourceVariableName)
				#~ weight= pcr.scalar(0)
				#~ iCnt= 0
				#~ ncDates= ncr.getNCDates(ncInFile).tolist()
				#~ for ncDate in ncDates:
					#~ if ncDate.year == patchYear:
						#~ band= ncDates.index(ncDate)+1
						#~ valueField= cellArea*getattr(spatialDataSet(dummyVariableName,\
							#~ ncDataSet,'FLOAT32', 'SCALAR',\
							#~ cloneAttributes.xLL, cloneAttributes.xUR, cloneAttributes.yLL, cloneAttributes.yUR,\
							#~ cloneAttributes.xResolution, cloneAttributes.yResolution,\
							#~ pixels= cloneAttributes.numberCols, lines= cloneAttributes.numberRows, band= band), dummyVariableName)
						#~ weight+= valueField
						#~ iCnt+= 1
				#~ weight/= iCnt
				#~ weight= pcr.areatotal(weight, fpuCode)
				#~ #-update reference value
				#~ pcr.aguila(referenceValues[sector], pcr.cover(weight/indexValue, 1.0))
				#~ referenceValues[sector]*= pcr.cover(weight/indexValue, 1.0)
