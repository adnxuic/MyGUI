function [func_str, coeff_names, option_json] = get_func(func_name)

% 设置 fittype 和选项。
ft = fittype(func_name);
func_str = formula(ft);
coeff_names = coeffnames(ft);
option_json = encode_fit_option_metadata(func_name, coeff_names);

end

function option_json = encode_fit_option_metadata(func_name, coeff_names)
opts = fitoptions(func_name);
coeff_count = numel(coeff_names);

metadata = struct();
metadata.Method = option_value(opts, "Method", fallback_method(func_name));
metadata.Normalize = option_value(opts, "Normalize", "off");
metadata.Robust = option_value(opts, "Robust", "Off");
metadata.Lower = option_vector(opts, "Lower", coeff_count, -Inf);
metadata.Upper = option_vector(opts, "Upper", coeff_count, Inf);
metadata.TolCon = option_value(opts, "TolCon", 1e-6);

if has_option(opts, "StartPoint")
    metadata.StartPoint = option_vector(opts, "StartPoint", coeff_count, NaN);
else
    metadata.StartPoint = {};
end

if has_option(opts, "Algorithm")
    metadata.Algorithm = option_value(opts, "Algorithm", "Trust-Region");
    metadata.DiffMinChange = option_value(opts, "DiffMinChange", 1e-8);
    metadata.DiffMaxChange = option_value(opts, "DiffMaxChange", 0.1);
    metadata.Display = option_value(opts, "Display", "Notify");
    metadata.MaxFunEvals = option_value(opts, "MaxFunEvals", 600);
    metadata.MaxIter = option_value(opts, "MaxIter", 400);
    metadata.TolFun = option_value(opts, "TolFun", 1e-6);
    metadata.TolX = option_value(opts, "TolX", 1e-6);
end

option_json = jsonencode(metadata);
end

function exists = has_option(opts, name)
exists = isprop(opts, char(name));
end

function value = option_value(opts, name, default_value)
if has_option(opts, name)
    raw_value = opts.(char(name));
    if isempty(raw_value)
        value = default_value;
    else
        value = raw_value;
    end
else
    value = default_value;
end
if isstring(value)
    value = char(value);
end
end

function values = option_vector(opts, name, expected_count, empty_fill)
values = {};
if ~has_option(opts, name)
    return;
end

raw_values = opts.(char(name));
if isempty(raw_values)
    if isnan(empty_fill)
        return;
    end
    raw_values = repmat(empty_fill, 1, expected_count);
end

raw_values = double(raw_values(:))';
values = cell(1, numel(raw_values));
for index = 1:numel(raw_values)
    values{index} = encode_number(raw_values(index));
end
end

function value = encode_number(number)
if isnan(number)
    value = [];
elseif isinf(number) && number > 0
    value = "Inf";
elseif isinf(number) && number < 0
    value = "-Inf";
else
    value = number;
end
end

function method = fallback_method(func_name)
func_name = char(func_name);
if startsWith(func_name, "poly") || strcmp(func_name, "log")
    method = "LinearLeastSquares";
else
    method = "NonlinearLeastSquares";
end
end


