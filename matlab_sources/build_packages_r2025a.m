% Build MATLAB Compiler SDK Python packages for the GUI MATLAB adapter.
% Run this file from MATLAB R2025a:
%
%   run(fullfile(pwd, "matlab_sources", "build_packages_r2025a.m"))
%
% The output directory is timestamped so existing generated packages are not
% overwritten accidentally.

repoRoot = fileparts(fileparts(mfilename("fullpath")));
sourceDir = fullfile(repoRoot, "matlab_sources");
buildRoot = fullfile(sourceDir, "r2025a_build_" + string(datetime("now", "Format", "yyyyMMdd_HHmmss")));

if ~isfolder(buildRoot)
    mkdir(buildRoot);
end

getFuncSource = fullfile(sourceDir, "get_func.m");
curveFittingSource = fullfile(sourceDir, "curve_fitting.m");

assert(isfile(getFuncSource), "Missing MATLAB source: %s", getFuncSource);
assert(isfile(curveFittingSource), "Missing MATLAB source: %s", curveFittingSource);

disp("Building get_func Python package...");
compiler.build.pythonPackage(getFuncSource, ...
    "PackageName", "get_func", ...
    "OutputDir", buildRoot, ...
    "Verbose", "on");

disp("Building curve_fitting Python package...");
compiler.build.pythonPackage(curveFittingSource, ...
    "PackageName", "curve_fitting", ...
    "OutputDir", buildRoot, ...
    "Verbose", "on");

disp("Build complete.");
disp("Generated packages:");
disp(fullfile(buildRoot, "get_funcpythonPackage", "get_func"));
disp(fullfile(buildRoot, "curve_fittingpythonPackage", "curve_fitting"));
disp("Copy only __init__.py and *.ctf from those package folders into:");
disp(fullfile(repoRoot, "mygui", "database", "matlab_func", "get_func"));
disp(fullfile(repoRoot, "mygui", "database", "matlab_func", "curve_fitting"));
