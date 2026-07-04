function [fit_func, fit_coes_name, fit_coes_val, gof_json, confidence_bounds, option_json] = curve_fitting(x, y, fit_type, options_json)

if nargin < 4
    options_json = "";
end

[xData, yData] = prepareCurveData( x, y );

% Build the fit type and options, then apply options_json overrides.
ft = fittype(fit_type);
opts = fitoptions(fit_type);

opts = apply_fit_options(opts, options_json);

% Run the curve fit and return structured result details.
[fitresult, gof] = fit( xData, yData, ft, opts );

fit_func = formula(fitresult);
fit_coes_name = coeffnames(fitresult);
fit_coes_val = coeffvalues(fitresult);
gof_json = encode_gof(gof);
confidence_bounds = coefficient_confidence_bounds(fitresult, fit_coes_name);
option_json = jsonencode(struct("Method", option_value(opts, "Method", ""), ...
    "Normalize", option_value(opts, "Normalize", ""), ...
    "Robust", option_value(opts, "Robust", "")));

end

function opts = apply_fit_options(opts, options_json)
options_text = char(options_json);
if isempty(strtrim(options_text))
    return;
end

options = jsondecode(options_text);
opts = apply_option(opts, options, "Normalize");
opts = apply_option(opts, options, "Robust");
opts = apply_option(opts, options, "Algorithm");
opts = apply_option(opts, options, "DiffMinChange");
opts = apply_option(opts, options, "DiffMaxChange");
opts = apply_option(opts, options, "Display");
opts = apply_option(opts, options, "MaxFunEvals");
opts = apply_option(opts, options, "MaxIter");
opts = apply_option(opts, options, "TolFun");
opts = apply_option(opts, options, "TolX");
opts = apply_option(opts, options, "TolCon");
opts = apply_numeric_array_option(opts, options, "Lower");
opts = apply_numeric_array_option(opts, options, "Upper");
opts = apply_numeric_array_option(opts, options, "StartPoint");
end

function opts = apply_option(opts, options, name)
field = char(name);
if ~isfield(options, field) || ~has_option(opts, field)
    return;
end

value = options.(field);
if isempty(value)
    return;
end
opts.(field) = value;
end

function opts = apply_numeric_array_option(opts, options, name)
field = char(name);
if ~isfield(options, field) || ~has_option(opts, field)
    return;
end

value = options.(field);
if isempty(value)
    return;
end

numeric_value = json_numeric_row(value);
if isempty(numeric_value)
    return;
end
opts.(field) = numeric_value;
end

function values = json_numeric_row(value)
if isnumeric(value)
    values = double(value(:))';
    return;
end
if isstring(value)
    value = cellstr(value);
end
if ischar(value)
    value = {value};
end
if iscell(value)
    values = zeros(1, numel(value));
    for index = 1:numel(value)
        values(index) = json_numeric_scalar(value{index});
    end
    return;
end
values = [];
end

function number = json_numeric_scalar(value)
if isnumeric(value)
    if isempty(value)
        number = NaN;
    else
        number = double(value(1));
    end
    return;
end

if isstring(value)
    value = char(value);
end
text = strtrim(char(value));
if strcmpi(text, "Inf") || strcmpi(text, "+Inf")
    number = Inf;
elseif strcmpi(text, "-Inf")
    number = -Inf;
elseif isempty(text)
    number = NaN;
else
    number = str2double(text);
end
end

function exists = has_option(opts, name)
exists = isprop(opts, char(name));
end

function value = option_value(opts, name, default_value)
if has_option(opts, name)
    value = opts.(char(name));
    if isempty(value)
        value = default_value;
    end
else
    value = default_value;
end
if isstring(value)
    value = char(value);
end
end

function gof_json = encode_gof(gof)
gof_struct = struct();
gof_struct.sse = gof.sse;
gof_struct.rsquare = gof.rsquare;
gof_struct.dfe = gof.dfe;
gof_struct.adjrsquare = gof.adjrsquare;
gof_struct.rmse = gof.rmse;
gof_json = jsonencode(gof_struct);
end

function confidence_bounds = coefficient_confidence_bounds(fitresult, fit_coes_name)
try
    confidence_bounds = confint(fitresult, 0.95);
catch
    confidence_bounds = nan(2, numel(fit_coes_name));
end
end
