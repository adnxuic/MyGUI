function [func_str,coeff_names] = get_func(func_name)

% 设置 fittype 和选项。
ft = fittype( func_name );
func_str = formula(ft);
coeff_names = coeffnames(ft);


