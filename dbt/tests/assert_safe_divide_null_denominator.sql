select 'safe_divide should return null for zero denominator' as failure
where {{ safe_divide('1', '0') }} is not null

union all

select 'safe_divide should return null for missing denominator' as failure
where {{ safe_divide('1', 'cast(null as integer)') }} is not null

union all

select 'safe_divide should preserve numerator arithmetic precedence' as failure
where {{ safe_divide('10 - 5', '5') }} <> 1
