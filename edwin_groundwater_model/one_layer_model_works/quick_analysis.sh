mkdir analysis
mkdir analysis/head_decline
cd analysis/head_decline
cdo yearavg ../../netcdf/groundwaterHead_monthEnd_output.nc groundwaterHead_annuaAvg_output_1995to2010.nc
cdo trend groundwaterHead_annuaAvg_output_1995to2010.nc groundwaterHead_annuaAvg_output_1995to2010_trend_a.nc groundwaterHead_annuaAvg_output_1995to2010_trend_b.nc
