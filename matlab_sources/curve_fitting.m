function [fit_func,fit_coes_name,fit_coes_val,gof] = curve_fitting(x, y, fit_type, ...
    isdefault, up_limit, down_limit, start_limit)

[xData, yData] = prepareCurveData( x, y );

% 设置 fittype 和选项。
ft = fittype(fit_type);
opts = fitoptions(fit_type);

% 如果不是默认设置，则设置上下限和起点（poly和log没有起点）
if ~isdefault
    if ~isempty(up_limit)
        opts.Upper = up_limit;
    end
    if ~isempty(down_limit)
        opts.Lower = down_limit;
    end
    if ~isempty(start_limit) && ~ismember(fit_type, {'poly', 'log'})
        opts.StartPoint = start_limit;
    end
end

% 对数据进行模型拟合。
[fitresult, gof] = fit( xData, yData, ft, opts );

fit_func = formula(fitresult);
fit_coes_name = coeffnames(fitresult);
fit_coes_val = coeffvalues(fitresult);
