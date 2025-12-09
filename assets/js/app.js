;(function() {
    'use strict';
    
    let analysisResults = {};
    let contentGapSkuCounts = null;
    let contentGapTopicSkuIds = {};
    let contentGapGroupSkuIds = {};
    let contentGapTopicSkuIdKeywordMap = {};
    let contentGapGroupSkuIdKeywordMap = {};
    let pollingInterval = null;
    let tableState = {
        fullData: [], headers: [], sortKey: null, sortDir: 'desc',
        searchTerm: '', searchKey: null, currentPage: 1, rowsPerPage: 25,
        timeframe: 'monthly',
        hideFeatures: false,
        hideZeroValueColumns: false,
        activeLens: null,
        rowEditState: null,
        interactiveHeaders: []
    };
    let overrideRules = [];
    let smartRecommendations = [];
    let smartRecommendationSelections = new Set();
    let inProductNameFacets = new Set(); // To store state of "In Product Name" checkboxes
    let isActiveRulesCollapsed = false; // Track collapsed/expanded state of Active Rules section
    const API_KEY = "my-secret-dev-key"; 
    const ui = {
        controlsContainer: document.getElementById('controls-container'),
        progressContainer: document.getElementById('progress-container'),
        resultsContainer: document.getElementById('results-container'),
        keywordModal: document.getElementById('keyword-modal'),
        modalTitle: document.getElementById('modal-title'),
        modalKeywordList: document.getElementById('modal-keyword-list'),
        modalCloseBtn: document.getElementById('modal-close-btn'),
    };
    
    const GAP_ANALYSIS_CAVEAT = "<b>Important Context:</b> A 'gap' (a keyword we don't rank for) doesn't automatically mean we don't offer the relevant product or service. Gaps can appear for several reasons: <ul class='list-disc'><li class='ml-4 my-1'><b>Focused Analysis:</b> Due to the large size of our and our competitors' websites, an analysis is often focused on a specific part of the site (e.g., specific departments or page types).</li><li class='ml-4 my-1'><b>Ranking Fluctuations:</b> Our domain may have ranked for the term previously but dropped out of the results at the time of the data export.</li><li class='ml-4 my-1'><b>No Dedicated Page:</b> We may offer the product or service, but lack a specific page optimised to meet the search intent for that exact keyword.</li></ul>";
    
    window.loadDefaultExclusions = function() {
        const template = document.getElementById('default-exclusions-template');
        const textarea = document.getElementById('branded-exclusions');
        if (template && textarea) {
            textarea.value = template.content.textContent.trim();
        }
    }

    function applyOverridesAndMerge(data, headers, hasOnsite, excludeFromAggregation = []) {
        // If no rules AND no columns to exclude, just return a copy
        if ((!overrideRules || overrideRules.length === 0) && excludeFromAggregation.length === 0) {
            return JSON.parse(JSON.stringify(data));
        }

        const aggregationMap = new Map();
        // Filter out columns that should be excluded from aggregation (e.g., hidden columns)
        const facetHeaders = headers.filter(h => 
            h !== 'Category Mapping' && !h.includes('Traffic') && !h.includes('Searches') && h !== 'KeywordDetails' &&
            !excludeFromAggregation.includes(h)
        );

        const metricCols = [
            'Monthly Organic Traffic', 'Total Monthly Google Searches',
            ...(hasOnsite ? ['Total On-Site Searches'] : [])
        ];

        const originalData = JSON.parse(JSON.stringify(data));

        originalData.forEach(originalRow => {
            let modifiedFacets = { 'Category Mapping': originalRow['Category Mapping'] };
            facetHeaders.forEach(h => { modifiedFacets[h] = originalRow[h]; });
            
            // Track if this row should be completely removed
            let shouldRemoveRow = false;

            overrideRules.forEach(rule => {
                if (!matchesRuleConditions(rule, modifiedFacets)) {
                    return;
                }
                const cellValue = modifiedFacets[rule.sourceColumn];
                const isCellBlank = cellValue === null || cellValue === undefined || String(cellValue).trim() === '';
                const ruleValue = String(rule.value).trim();
                
                const cellValues = isCellBlank ? [] : String(cellValue).split(' | ').map(v => v.trim());

                const isMatch = (ruleValue === '' && isCellBlank) || (ruleValue !== '' && !isCellBlank && cellValues.includes(ruleValue));

                if (isMatch) {
                    if (rule.action === 'change') {
                        if (ruleValue === '') { // This rule changes a blank value
                            modifiedFacets[rule.sourceColumn] = rule.newValue.trim();
                        } else { // This rule changes a specific, existing value
                            const newValues = cellValues.map(v => (v === ruleValue ? rule.newValue.trim() : v));
                            modifiedFacets[rule.sourceColumn] = newValues.join(' | ');
                        }
                    } else if (rule.action === 'remove') {
                        // DELETE AND REMOVE: Mark row for complete removal from dataset
                        if (ruleValue !== '' && !isCellBlank && cellValues.includes(ruleValue)) {
                            shouldRemoveRow = true;
                        }
                    } else if (ruleValue !== '') { // MOVE and DELETE only make sense for non-blank values
                        const newSourceValues = cellValues.filter(v => v !== ruleValue);
                        modifiedFacets[rule.sourceColumn] = newSourceValues.length > 0 ? newSourceValues.join(' | ') : null;

                        if (rule.action === 'move') {
                            const existingTargetValue = modifiedFacets[rule.targetColumn];
                            
                            if (rule.moveMode === 'replace') {
                                // MOVE AND REPLACE: Replace the entire target column value
                                modifiedFacets[rule.targetColumn] = ruleValue;
                            } else {
                                // MOVE AND APPEND (default): Append to existing values with pipe separator
                                const existingTargetValues = (!existingTargetValue || String(existingTargetValue).trim() === '') ? [] : String(existingTargetValue).split(' | ').map(v => v.trim());
                                if (!existingTargetValues.includes(ruleValue)) {
                                    existingTargetValues.push(ruleValue);
                                }
                                modifiedFacets[rule.targetColumn] = existingTargetValues.sort().join(' | ');
                            }
                        }
                    }
                }
            });
            
            // Skip adding this row if it's marked for removal
            if (shouldRemoveRow) {
                return;
            }
            
            const key = [modifiedFacets['Category Mapping'] || '', ...facetHeaders.map(h => modifiedFacets[h] || '')].join('||');
            
            if (aggregationMap.has(key)) {
                const existing = aggregationMap.get(key);
                metricCols.forEach(mCol => {
                    existing[mCol] = (existing[mCol] || 0) + (originalRow[mCol] || 0);
                });
                if (originalRow.KeywordDetails) {
                   existing.KeywordDetails.push(...originalRow.KeywordDetails);
                }
            } else {
                const newEntry = { ...originalRow, ...modifiedFacets };
                newEntry.KeywordDetails = [...(originalRow.KeywordDetails || [])];
                aggregationMap.set(key, newEntry);
            }
        });

        return Array.from(aggregationMap.values());
    }


    function getFilteredData() {
        let filteredData = [...tableState.fullData];
        const annualTrafficHeader = updateHeadersForTimeframe(['Monthly Organic Traffic'], 'annual')[0];
        const monthlyTrafficHeader = updateHeadersForTimeframe(['Monthly Organic Traffic'], 'monthly')[0];

        if (tableState.hideZeroTraffic) {
            filteredData = filteredData.filter(row => {
                const traffic = row[annualTrafficHeader] || row[monthlyTrafficHeader];
                return typeof traffic === 'number' && traffic > 0;
            });
        }

        if (tableState.searchTerm && tableState.searchKey) {
            const term = tableState.searchTerm;
            let filterFn;
            try {
                const regex = new RegExp(term, 'i');
                filterFn = (val) => regex.test(val);
            } catch (e) {
                filterFn = (val) => val.toLowerCase().includes(term.toLowerCase());
            }
            filteredData = filteredData.filter(row => {
                const val = row[tableState.searchKey];
                return val && filterFn(val.toString());
            });
        }
        if (tableState.sortKey) {
            const currentSortKeyBase = tableState.sortKey.replace('Annual', 'Monthly').split(' (')[0]; 

            const numericHeadersBase = [
                'Monthly Google Searches', 'Highest Competitor Rank', 'Top Competitor Monthly Organic Traffic', '# Ranking Competitors',
                'Opportunity Score', 'On-Site Searches', 'Total Monthly Google Searches', 'Total On-Site Searches',
                'Total Competitor Monthly Organic Traffic', 'Gap Keyword Count', 'Competitor Avg. Rank', 'Our Rank',
                'Our Monthly Organic Traffic', 'Best Competitor Monthly Organic Traffic',
                'Monthly Traffic Growth Opportunity', 'Keyword Count', 'Avg Our Rank', 'Total Our Monthly Traffic',
                'Avg Best Competitor Rank', 'Total Best Competitor Monthly Traffic', 'Total Monthly Traffic Growth Opportunity',
                'Total Monthly Google Traffic', 'Monthly Organic Traffic', 'Facet Value Score'
            ];
            const isNumeric = numericHeadersBase.includes(currentSortKeyBase);
            const isMarketShareCol = tableState.competitorDomainHeaders && tableState.competitorDomainHeaders.includes(tableState.sortKey);

            filteredData.sort((a, b) => {
                const valA = a[tableState.sortKey];
                const valB = b[tableState.sortKey];

                if (isNumeric) {
                    const cleanValA = String(valA).replace(/<[^>]*>?/gm, '').replace(/,/g, '').replace(/%/g, '');
                    const cleanValB = String(valB).replace(/<[^>]*>?/gm, '').replace(/,/g, '').replace(/%/g, '');
                    const numA = (cleanValA === '' || cleanValA === null || cleanValA === undefined) ? -Infinity : parseFloat(cleanValA);
                    const numB = (cleanValB === '' || cleanValB === null || cleanValB === undefined) ? -Infinity : parseFloat(cleanValB);
                    return tableState.sortDir === 'asc' ? numA - numB : numB - numA;
                } else if (isMarketShareCol) {
                    const numA = valA ? parseFloat(valA[0]) : -Infinity;
                    const numB = valB ? parseFloat(valB[0]) : -Infinity;
                    return tableState.sortDir === 'asc' ? numA - numB : numB - numA;
                }
                else {
                    const strA = (valA || '').toString().toLowerCase().replace(/<[^>]*>?/gm, '');
                    const strB = (valB || '').toString().toLowerCase().replace(/<[^>]*>?/gm, '');
                    if (strA < strB) return tableState.sortDir === 'asc' ? -1 : 1;
                    if (strA > strB) return tableState.sortDir === 'asc' ? 1 : -1;
                    return 0;
                }
            });
        }
        return filteredData;
    }
    
    function calculateTotalRow(headers, data) {
        const totals = {};
        const summationBases = ['Google Searches', 'Organic Traffic', 'On-Site Searches', 'Gap Keyword Count', 'Growth Opportunity', 'Keyword Count', 'Total Our', 'Total Best Competitor', 'Total Google Traffic'];
        const averageBases = ['Rank', 'Score', '# Ranking Competitors'];
        
        const totalTrafficHeader = headers.find(h => h.includes('Total') && h.includes('Google Traffic'));
        const grandTotalTraffic = data.reduce((sum, row) => sum + (row[totalTrafficHeader] || 0), 0);
        
        headers.forEach(header => {
            const isMarketShareCol = tableState.competitorDomainHeaders && tableState.competitorDomainHeaders.includes(header);
            
            if (isMarketShareCol) {
                const competitorTotalTraffic = data.reduce((sum, row) => sum + (row[header] ? row[header][1] : 0), 0);
                const overallShare = grandTotalTraffic > 0 ? (competitorTotalTraffic / grandTotalTraffic) * 100 : 0;
                totals[header] = `${overallShare.toFixed(1)}% (${(competitorTotalTraffic || 0).toLocaleString()})`;
                return;
            }

            const isSummationCol = summationBases.some(base => header.includes(base));
            const isAverageCol = averageBases.some(base => header.includes(base));

            const values = data.map(row => {
                const rawValue = row[header];
                const cleanValue = parseFloat(String(rawValue).replace(/<[^>]*>?/gm, '').replace(/,/g, ''));
                return isNaN(cleanValue) ? 0 : cleanValue;
            });
            
            if (isSummationCol) {
                const total = values.reduce((sum, val) => sum + val, 0);
                totals[header] = Math.round(total).toLocaleString();
            } else if (isAverageCol) {
                const sum = values.reduce((sum, val) => sum + val, 0);
                const total = data.length > 0 ? sum / data.length : 0;
                totals[header] = total.toFixed(1);
            } else {
                totals[header] = '';
            }
        });
        totals[headers[0]] = 'Total';
        return totals;
    }

    function createNestedKeywordTable(keywordDetails) {
         if (!keywordDetails || keywordDetails.length === 0) {
            return '<div class="p-4 text-center text-gray-500">No keyword details available.</div>';
        }
        
        let currentHeaders = ['Keyword', 'Monthly Google Searches', 'On-Site Searches', 'Monthly Organic Traffic', 'Top Ranking Competitor', 'Rank', 'URL'];
        let headers = updateHeadersForTimeframe(currentHeaders, tableState.timeframe);

        let tableHtml = '<table class="nested-table"><thead><tr>';
        headers.forEach(h => tableHtml += `<th>${h}</th>`);
        tableHtml += '</tr></thead><tbody>';

        keywordDetails.forEach(kw => {
            tableHtml += `<tr>
                <td>${kw.Keyword || ''}</td>
                <td>${(Math.round(kw[headers[1]] || 0)).toLocaleString()}</td>
                <td>${(kw[headers[2]] || 0).toLocaleString()}</td>
                <td>${(Math.round(kw[headers[3]] || 0)).toLocaleString()}</td>
                <td>${kw['Top Ranking Competitor'] || ''}</td>
                <td>${kw.Rank || ''}</td>
                <td><a href="${kw.URL}" target="_blank" class="text-blue-600 hover:underline break-all">${kw.URL}</a></td>
            </tr>`;
        });

        tableHtml += '</tbody></table>';
        return tableHtml;
    }

    function createNestedFacetValueTable(facetValueDetails) {
        if (!facetValueDetails || facetValueDetails.length === 0) {
            return '<div class="p-4 text-center text-gray-500">No facet value details available.</div>';
        }

        const hasOnsiteData = facetValueDetails[0].hasOwnProperty('Total On-Site Searches') || facetValueDetails[0].hasOwnProperty('Total Annual On-Site Searches');
        let headers = ['Facet Value', 'Keyword Count', 'Monthly Organic Traffic', 'Total Monthly Google Searches'];
        if (hasOnsiteData) headers.push('Total On-Site Searches');
        let displayHeaders = updateHeadersForTimeframe(headers, tableState.timeframe);

        let tableHtml = '<table class="nested-table"><thead><tr>';
        displayHeaders.forEach(h => tableHtml += `<th>${h}</th>`);
        tableHtml += '</tr></thead><tbody>';

        facetValueDetails.forEach(detail => {
            tableHtml += `<tr>
                <td class="font-semibold">${detail['Facet Value'] || ''}</td>
                <td>${(detail['Keyword Count'] || 0).toLocaleString()}</td>
                <td>${(Math.round(detail[displayHeaders[2]] || 0)).toLocaleString()}</td>
                <td>${(Math.round(detail[displayHeaders[3]] || 0)).toLocaleString()}</td>
                ${hasOnsiteData ? `<td>${(Math.round(detail[displayHeaders[4]] || 0)).toLocaleString()}</td>` : ''}
            </tr>`;
        });

        tableHtml += '</tbody></table>';
        return tableHtml;
    }

    function createTableFromArray(data, headers, fullFilteredData) {
        if (!data || data.length === 0) return `<div class="text-center text-gray-500 p-8 border rounded-lg bg-gray-50">No results match your search.</div>`;
        
        const isNestableReport = data[0] && (data[0].hasOwnProperty('KeywordDetails') || data[0].hasOwnProperty('FacetValueDetails'));
        const isFacetPotentialReport = data[0] && data[0].hasOwnProperty('FacetValueDetails');
        const showRowActions = tableState.activeLens === 'interactive-matrix';
        
        const baseFacetHeaders = ['Category Mapping', 'Facet Type', 'Monthly Organic Traffic', 'Total Monthly Google Searches', 'Total On-Site Searches', 'Facet Value Score'];
        
        const facetHeaders = isNestableReport 
            ? headers.filter(h => {
                const baseHeaderForCheck = h.replace('Annual', 'Monthly');
                return !baseFacetHeaders.some(base => baseHeaderForCheck.includes(base));
              })
            : [];
        
        let headerHtml = '';

        if (isNestableReport) {
            headerHtml += `<th class="p-3 w-8"></th>`; 
        }
        headerHtml += headers.map(h => {
            const isSorted = h === tableState.sortKey;
            const sortIcon = isSorted ? (tableState.sortDir === 'asc' ? '▲' : '▼') : '';
            return `<th data-sort-key="${h}" class="p-3 text-left text-xs font-bold uppercase ${isSorted ? 'sorted' : ''}">${h.replace(/_/g, ' ')} <span class="sort-icon">${sortIcon}</span></th>`;
        }).join('');
        
        if (isFacetPotentialReport) {
            headerHtml += `<th class="p-3 text-left text-xs font-bold uppercase">In Product Name</th>`;
        }
        if (showRowActions) {
            headerHtml += `<th class="p-3 text-left text-xs font-bold uppercase">Actions</th>`;
        }

        let bodyHtml = '';
        data.forEach(row => {
            let cells = '';
            if (isNestableReport) {
                const hasDetails = (row.KeywordDetails && row.KeywordDetails.length > 0) || (row.FacetValueDetails && row.FacetValueDetails.length > 0);
                cells += `<td class="p-3 text-center">
                    <button class="keyword-details-toggle" ${!hasDetails ? 'disabled' : ''}>
                        <svg class="h-4 w-4 ${hasDetails ? 'text-gray-600' : 'text-gray-300'}" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path></svg>
                    </button>
                </td>`;
            }

            cells += headers.map(h => {
                let val = row[h];
                let cellClass = 'p-3 border-t text-sm';
                const isFacetColumn = isNestableReport && facetHeaders.includes(h);

                const baseHeader = h.replace('Annual', 'Monthly').replace(/ \(.+\)$/, '');
                const isKnownMetric = monthlyToAnnualCols.includes(baseHeader) || 
                                      h.includes('On-Site Searches') ||
                                      h.includes('Keyword Count') ||
                                      h === '# Ranking Competitors' ||
                                      h === 'Opportunity Score' ||
                                      h === 'Facet Value Score';

                if (isFacetColumn) {
                    cellClass += ' facet-cell';
                    if (val === null || val === undefined || String(val).trim() === '') {
                        cellClass += ' empty';
                        val = '—';
                    }
                } else if (Array.isArray(val)) { 
                    val = `${val[0].toFixed(1)}% (${(val[1] || 0).toLocaleString()})`;
                } else if (isKnownMetric && !h.toLowerCase().includes('rank')) {
                    // FIX: Do not attempt to format a value that is already HTML (like our button)
                    if (typeof val === 'string' && val.startsWith('<button')) {
                        // Keep the value as is.
                    } else {
                        val = Math.round(Number(val) || 0).toLocaleString();
                    }
                }
                
                return `<td class="${cellClass}">${val !== null && val !== undefined ? val : ''}</td>`;
            }).join('');
            
            if (isFacetPotentialReport) {
                const facetKey = `${row['Category Mapping']}||${row['Facet Type']}`;
                const isChecked = inProductNameFacets.has(facetKey);
                cells += `<td class="p-3 border-t text-sm text-center">
                    <input type="checkbox" class="in-product-name-toggle h-4 w-4" data-facet-key="${facetKey}" ${isChecked ? 'checked' : ''}>
                </td>`;
            }
            if (showRowActions) {
                const rowId = typeof row.__rowId === 'number' ? row.__rowId : '';
                cells += `<td class="p-3 border-t text-sm">
                    <button class="row-edit-btn inline-flex items-center px-3 py-1 border border-blue-300 text-blue-700 rounded hover:bg-blue-50 text-xs font-semibold" data-row-id="${rowId}">Edit Row</button>
                </td>`;
            }

            bodyHtml += `<tr class="hover:bg-gray-50">${cells}</tr>`;

            if (isNestableReport) {
                let nestedHtml = '';
                if (row.KeywordDetails) {
                    nestedHtml = createNestedKeywordTable(row.KeywordDetails);
                } else if (row.FacetValueDetails) {
                    nestedHtml = createNestedFacetValueTable(row.FacetValueDetails);
                }
                const extraCols = (isNestableReport ? 1 : 0) + (isFacetPotentialReport ? 1 : 0) + (showRowActions ? 1 : 0);
                bodyHtml += `<tr class="keyword-details-row"><td colspan="${headers.length + extraCols}" class="keyword-details-cell">${nestedHtml}</td></tr>`;
            }
        });
        
        let footerHtml = '';
        if (fullFilteredData && fullFilteredData.length > 0) {
            const totalRowData = calculateTotalRow(headers, fullFilteredData);
            let footerCells = '';
            if(isNestableReport) footerCells += '<td></td>';
            footerCells += headers.map(h => `<td class="p-3 text-sm">${totalRowData[h]}</td>`).join('');
            if(isFacetPotentialReport) footerCells += '<td></td>';
             if (showRowActions) footerCells += '<td></td>';
            footerHtml = `<tfoot><tr>${footerCells}</tr></tfoot>`;
        }

        return `<div class="overflow-x-auto border rounded-lg"><table class="w-full"><thead><tr class="bg-gray-50">${headerHtml}</tr></thead><tbody>${bodyHtml}</tbody>${footerHtml}</table></div>`;
    }

    function createPaginationControls(filteredRowCount) {
        if (filteredRowCount === 0) return '';
        const totalPages = Math.ceil(filteredRowCount / tableState.rowsPerPage);
        const startRow = (tableState.currentPage - 1) * tableState.rowsPerPage + 1;
        const endRow = Math.min(startRow + tableState.rowsPerPage - 1, filteredRowCount);
        return `<div class="text-sm text-gray-700">Showing <span class="font-medium">${startRow}</span> to <span class="font-medium">${endRow}</span> of <span class="font-medium">${filteredRowCount}</span> results</div><div class="flex items-center space-x-2"><button data-pagination-action="prev" class="pagination-btn text-sm font-semibold py-1 px-3 rounded border border-gray-300 hover:bg-gray-100" ${tableState.currentPage === 1 ? 'disabled' : ''}>Previous</button><span class="text-sm">Page ${tableState.currentPage} of ${totalPages}</span><button data-pagination-action="next" class="pagination-btn text-sm font-semibold py-1 px-3 rounded border border-gray-300 hover:bg-gray-100" ${totalPages === 0 || tableState.currentPage === totalPages ? 'disabled' : ''}>Next</button><select id="rows-per-page-select" class="text-sm p-1 border-gray-300 rounded-md"><option value="25" ${tableState.rowsPerPage === 25 ? 'selected' : ''}>25 / page</option><option value="50" ${tableState.rowsPerPage === 50 ? 'selected' : ''}>50 / page</option><option value="100" ${tableState.rowsPerPage === 100 ? 'selected' : ''}>100 / page</option></select></div>`;
    }

    function createReportContainer(title, subtitle, customContent = '', extraDescription = '') {
        const regexTipHtml = `<div class="tooltip-container"><svg class="tooltip-icon h-5 w-5 text-gray-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd" /></svg><span class="tooltip-text"><b>Regex Search Tips:</b><br><code>^word</code> &ndash; Starts with 'word'<br><code>word$</code> &ndash; Ends with 'word'<br><code>word1|word2</code> &ndash; Has 'word1' or 'word2'<br><code>\\bword\\b</code> &ndash; Matches whole word</span></div>`;
        const timeframeToggle = `<div class="flex items-center"><span class="text-sm font-semibold mr-2">Timeframe:</span><button data-timeframe="monthly" class="scope-toggle-btn text-xs font-semibold py-1 px-3 rounded-l-md ${tableState.timeframe === 'monthly' ? 'active' : ''}">Monthly</button><button data-timeframe="annual" class="scope-toggle-btn text-xs font-semibold py-1 px-3 rounded-r-md ${tableState.timeframe === 'annual' ? 'active' : ''}">Annual</button></div>`;
        
        // Debug logging for save button creation
        console.log('Creating report container for:', title);
        console.log('Current project:', currentProject);
        console.log('Analysis results available:', analysisResults && Object.keys(analysisResults).length > 0);
        console.log('Has valid analysis data:', hasValidAnalysisData(analysisResults));
        
        const hasAnalysisResults = analysisResults && Object.keys(analysisResults).length > 0 && hasValidAnalysisData(analysisResults);
        const saveButton = currentProject && hasAnalysisResults ? `<button onclick="saveProjectState()" class="save-project-btn text-xs font-semibold py-1 px-3 rounded border border-green-300 hover:bg-green-100 text-green-700">💾 Save Project</button>` : '';
        
        console.log('Save button will be created:', !!saveButton);
        return `<div class="bg-white p-6 rounded-xl shadow-lg" data-report-title="${title}"><div class="flex flex-wrap justify-between items-center mb-6 border-b pb-4 gap-4"><div><h2 class="text-2xl font-bold">${title}</h2><p class="text-sm text-gray-600 mt-1">${subtitle}</p></div><div class="flex items-center space-x-2">${saveButton}<button data-export-type="excel" class="export-btn text-xs font-semibold py-1 px-3 rounded border border-gray-300 hover:bg-gray-100">Export Excel</button><button data-export-type="json" class="export-btn text-xs font-semibold py-1 px-3 rounded border border-gray-300 hover:bg-gray-100">Export JSON</button><button data-export-type="pdf" class="export-btn text-xs font-semibold py-1 px-3 rounded border border-gray-300 hover:bg-gray-100">Export PDF</button><button class="back-to-lenses-btn text-sm font-semibold text-blue-600 hover:underline">&larr; Back to Lenses</button></div></div>${extraDescription ? `<div class="text-sm text-gray-600 bg-blue-50 border border-blue-200 p-3 rounded-md mb-4">${extraDescription}</div>` : ''}<div id="manual-overrides-container" class="mb-6"></div><div class="flex flex-wrap justify-between items-center mb-4 gap-4"><div class="flex items-center gap-2"><input type="text" id="table-search-input" placeholder="Filter with text or regex..." class="w-full md:w-auto p-2 border rounded-md focus:ring-blue-500 focus:border-blue-500">${regexTipHtml}</div><div class="flex items-center gap-4">${customContent}${timeframeToggle}</div></div><div id="interactive-table-wrapper"></div><div id="pagination-controls-wrapper" class="flex flex-wrap justify-between items-center mt-4 gap-4"></div></div>`;
    }

    // Helper function to check if a category-facet combination has SKUs
    function normalizeSkuMatchValue(value) {
        if (value === null || value === undefined) return '';
        return String(value)
            .replace(/<[^>]*>?/gm, '')
            .toLowerCase()
            .replace(/&/g, ' and ')
            .replace(/[^a-z0-9]+/g, ' ')
            .trim();
    }

    function buildSkuMatchKey(category, facetAttribute, facetValue) {
        return [
            normalizeSkuMatchValue(category),
            normalizeSkuMatchValue(facetAttribute),
            normalizeSkuMatchValue(facetValue)
        ].join('|');
    }

    function hasSkusForCategoryFacet(category, facetValue, pimResults, facetAttribute = null) {
        if (!pimResults || !pimResults.category_facet_counts) return null;
        const normalizedCategory = normalizeSkuMatchValue(category);
        const normalizedFacetValue = normalizeSkuMatchValue(facetValue);
        const normalizedFacetAttribute = facetAttribute ? normalizeSkuMatchValue(facetAttribute) : null;
        
        // Find matching entry - must match Category Mapping, Facet Value, and Facet Attribute (if provided)
        // This prevents false matches like "Stone" (color) vs "Stone" (material)
        const matchingEntry = pimResults.category_facet_counts.find(entry => {
            const categoryMatch = normalizeSkuMatchValue(entry['Category Mapping']) === normalizedCategory;
            const valueMatch = normalizeSkuMatchValue(entry['Facet Value']) === normalizedFacetValue;
            
            // If facetAttribute is provided, must match (exact or semantic match)
            // If not provided, any Facet Attribute is acceptable (fallback)
            let attributeMatch = true;
            if (facetAttribute) {
                const entryAttribute = normalizeSkuMatchValue(entry['Facet Attribute'] || '');
                attributeMatch = entryAttribute === normalizedFacetAttribute;
            }
            
            return categoryMatch && valueMatch && attributeMatch;
        });
        
        return matchingEntry ? (matchingEntry['SKU Count'] > 0) : null;
    }

    // Helper function to check if a row has any SKUs
    function rowHasSkus(row, keyGenHeaders, pimResults) {
        if (!pimResults || !pimResults.category_facet_counts) return null;
        
        const category = row['Category Mapping'] || '';
        const normalizedCategory = normalizeSkuMatchValue(category);
        
        const facetColumns = getFacetHeaders(keyGenHeaders);
        const normalizedRoot = normalizeSkuMatchValue('Root Category');
        
        // First, check if there's a Root Category match for this category
        // This handles cases where SKUs match the category but not specific facet combinations
        const rootCategoryMatch = pimResults.category_facet_counts.find(entry => 
            normalizeSkuMatchValue(entry['Category Mapping']) === normalizedCategory && 
            normalizeSkuMatchValue(entry['Facet Attribute']) === normalizedRoot && 
            normalizeSkuMatchValue(entry['Facet Value']) === normalizedRoot &&
            entry['SKU Count'] > 0
        );
        if (rootCategoryMatch) {
            return true;
        }
        
        // Check if any facet value in this row has SKUs
        // IMPORTANT: Must match both Facet Value AND Facet Attribute (column name) to prevent false matches
        for (const facetCol of facetColumns) {
            const facetValues = row[facetCol];
            if (facetValues) {
                const values = String(facetValues).split('|').map(v => v.trim()).filter(Boolean);
                for (const facetValue of values) {
                    // Pass the column name as facetAttribute to ensure correct matching
                    // E.g., "Stone" in "Colour" column should only match "Stone" with Facet Attribute "Colour", not "Stone" with Facet Attribute "Material"
                    if (hasSkusForCategoryFacet(category, facetValue, pimResults, facetCol) === true) {
                        return true;
                    }
                }
            }
        }
        
        // Check if row has any non-empty facets
        const hasFacets = facetColumns.some(col => {
            const facetValues = row[col];
            return facetValues && String(facetValues).trim() !== '';
        });
        
        // If no facets (or all facets are empty), check just the category
        // Note: Root Category already checked above, but also check for any other matches
        if ((facetColumns.length === 0 || !hasFacets) && category) {
            // Check if any entry has this category (with any facet or blank)
            // Root Category already checked, so this is just a fallback
            const hasMatch = pimResults.category_facet_counts.some(entry => 
                normalizeSkuMatchValue(entry['Category Mapping']) === normalizedCategory && entry['SKU Count'] > 0
            );
            return hasMatch;
        }
        
        return false;
    }

    async function exportCategoryOverhaulToExcel(data, headers, fileName) {
        if (typeof ExcelJS === 'undefined') {
            console.error('ExcelJS not loaded, falling back to basic export');
            // Fallback to basic XLSX export without colors
            const wb = XLSX.utils.book_new();
            const ws = XLSX.utils.json_to_sheet(data);
            XLSX.utils.book_append_sheet(wb, ws, "Category Matrix");
            XLSX.writeFile(wb, `${fileName}.xlsx`);
            return;
        }

        const workbook = new ExcelJS.Workbook();
        workbook.creator = 'SEO Analyzer';
        workbook.created = new Date();

        const createRowKey = (row, keyHeaders) => {
            const keyParts = [];
            keyHeaders.forEach(h => {
                const value = row[h];
                if (value && String(value).trim() !== '') {
                    keyParts.push(value);
                }
            });
            return keyParts.join(' | ');
        };

        // Get PIM results if available
        const pimResults = window.pimAnalysisResults || null;

        // Sheet 1: Category Matrix
        const worksheet1 = workbook.addWorksheet('Category Matrix');
        const topLevelHeaders = headers.filter(h => h !== ''); 
        const keyGenHeaders = topLevelHeaders.filter(h => !h.includes('Traffic') && !h.includes('Searches') && !h.includes('Score'));
        const topLevelData = data.map(row => {
            const newRow = {};
            topLevelHeaders.forEach(header => {
                const rawValue = row[header];
                newRow[header] = typeof rawValue === 'string' ? String(rawValue).replace(/<[^>]*>?/gm, '') : rawValue;
            });
            newRow['Category & Facet Key'] = createRowKey(row, keyGenHeaders);
            return newRow;
        });
        
        const allHeaders1 = [...topLevelHeaders, 'Category & Facet Key'];
        worksheet1.columns = allHeaders1.map(h => ({ header: h, key: h, width: 15 }));
        
        // Add header row first
        worksheet1.addRow(allHeaders1);
        const headerRow = worksheet1.getRow(1);
        headerRow.font = { bold: true };
        headerRow.fill = {
            type: 'pattern',
            pattern: 'solid',
            fgColor: { argb: 'FFD3D3D3' }
        };
        
        // Add data rows and apply red highlighting for rows without SKUs
        topLevelData.forEach((rowData, index) => {
            const excelRow = worksheet1.addRow(rowData);
            
            // Check if this row has associated SKUs
            if (pimResults) {
                const originalRow = data[index];
                const hasSkus = rowHasSkus(originalRow, keyGenHeaders, pimResults);
                
                // If PIM data exists and this row has no SKUs, highlight in red
                if (hasSkus === false) {
                    excelRow.fill = {
                        type: 'pattern',
                        pattern: 'solid',
                        fgColor: { argb: 'FFFFE5E5' }  // Light red background
                    };
                    excelRow.font = { color: { argb: 'FFCC0000' } };  // Dark red text
                }
            }
        });

        // Sheet 2: Keyword Breakdown
        const keywordBreakdownData = [];
        data.forEach(parentRow => {
            const rowKey = createRowKey(parentRow, keyGenHeaders);
            if (parentRow.KeywordDetails && parentRow.KeywordDetails.length > 0) {
                parentRow.KeywordDetails.forEach(keywordRow => {
                    const newBreakdownRow = {};
                    keyGenHeaders.forEach(pHeader => {
                        newBreakdownRow[pHeader] = parentRow[pHeader];
                    });
                    newBreakdownRow['Keyword'] = keywordRow['Keyword'] || '';
                    newBreakdownRow['Monthly Google Searches'] = keywordRow['Monthly Google Searches'] || 0;
                    newBreakdownRow['On-Site Searches'] = keywordRow['On-Site Searches'] || 0;
                    newBreakdownRow['Monthly Organic Traffic'] = keywordRow['Monthly Organic Traffic'] || 0;
                    newBreakdownRow['Top Ranking Competitor'] = keywordRow['Top Ranking Competitor'] || 'N/A';
                    newBreakdownRow['Rank'] = keywordRow['Rank'] || 'N/A';
                    newBreakdownRow['URL'] = keywordRow['URL'] || '#';
                    newBreakdownRow['Category & Facet Key'] = rowKey;
                    keywordBreakdownData.push(newBreakdownRow);
                });
            }
        });

        if (keywordBreakdownData.length > 0) {
            const worksheet2 = workbook.addWorksheet('Keyword Breakdown');
            const reorderedData = keywordBreakdownData.map(row => {
                const reorderedRow = {};
                reorderedRow['Category & Facet Key'] = row['Category & Facet Key'];
                reorderedRow['Keyword'] = row['Keyword'];
                Object.keys(row).forEach(key => {
                    if (key !== 'Category & Facet Key' && key !== 'Keyword') {
                        reorderedRow[key] = row[key];
                    }
                });
                return reorderedRow;
            });
            
            const allHeaders2 = Object.keys(reorderedData[0] || {});
            worksheet2.columns = allHeaders2.map(h => {
                let width = 12;
                if (h === 'Keyword') width = 30;
                else if (h === 'URL') width = 50;
                else if (h === 'Category & Facet Key') width = 25;
                else if (h.includes('Traffic') || h.includes('Searches')) width = 15;
                return { header: h, key: h, width };
            });
            worksheet2.addRows(reorderedData);
        }

        const categoryFacetPairs = buildCategoryFacetPairs(data, headers);
        if (categoryFacetPairs.length > 0) {
            const worksheetPairs = workbook.addWorksheet('Category-Facet Map');
            
            // Add SKU counts if PIM results are available
            const pimResults = window.pimAnalysisResults || null;
            if (pimResults && pimResults.category_facet_counts) {
                // Create a map for quick lookup (include Facet Attribute in key)
                const skuCountMap = new Map();
                pimResults.category_facet_counts.forEach(entry => {
                    const key = buildSkuMatchKey(entry['Category Mapping'], entry['Facet Attribute'] || '', entry['Facet Value']);
                    skuCountMap.set(key, {
                        count: entry['SKU Count'] || 0,
                        skuIds: entry['SKU IDs'] || [],
                        count: entry['SKU Count'] || 0
                    });
                });
                
                // Add SKU counts to pairs
                const pairsWithCounts = categoryFacetPairs.map(pair => {
                    const key = buildSkuMatchKey(pair['Category Mapping'], pair['Facet Attribute'] || '', pair['Facet Value']);
                    const skuData = skuCountMap.get(key);
                    return {
                        'Category Mapping': pair['Category Mapping'],
                        'Facet Attribute': pair['Facet Attribute'] || '',
                        'Facet Value': pair['Facet Value'],
                        'SKU Count': skuData ? skuData.count : 0,
                        'SKU IDs': (() => {
                            if (!skuData || !skuData.skuIds) return '(None)';
                            // Ensure skuIds is an array
                            const idsArray = Array.isArray(skuData.skuIds) ? skuData.skuIds : [];
                            // Filter out null/empty/NaN values
                            const validIds = idsArray.filter(id => {
                                if (id == null || id === '') return false;
                                const idStr = String(id).trim();
                                return idStr && idStr.toLowerCase() !== 'nan' && idStr !== 'undefined';
                            });
                            return validIds.length > 0 ? validIds.join(', ') : '(None)';
                        })()
                    };
                });
                
                worksheetPairs.columns = [
                    { header: 'Category Mapping', key: 'Category Mapping', width: 30 },
                    { header: 'Facet Attribute', key: 'Facet Attribute', width: 20 },
                    { header: 'Facet Value', key: 'Facet Value', width: 40 },
                    { header: 'SKU Count', key: 'SKU Count', width: 12 },
                    { header: 'SKU IDs', key: 'SKU IDs', width: 50 }
                ];
                worksheetPairs.addRows(pairsWithCounts);
            } else {
                worksheetPairs.columns = [
                    { header: 'Category Mapping', key: 'Category Mapping', width: 30 },
                    { header: 'Facet Attribute', key: 'Facet Attribute', width: 20 },
                    { header: 'Facet Value', key: 'Facet Value', width: 40 }
                ];
                worksheetPairs.addRows(categoryFacetPairs);
            }
        }

        // Sheet 3: Category Consolidation with colors
        console.log('Creating Category Consolidation view with colors...');
        const categoryConsolidationData = createCategoryConsolidationView(data, headers);
        if (categoryConsolidationData.length > 0) {
            await addColoredConsolidationSheetToWorkbook(workbook, categoryConsolidationData);
        }

        // Write file
        const buffer = await workbook.xlsx.writeBuffer();
        const blob = new Blob([buffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `${fileName}.xlsx`;
        link.click();
        window.URL.revokeObjectURL(url);
    }

    function buildCategoryFacetPairs(data = [], headers = []) {
        if (!Array.isArray(data) || data.length === 0) return [];
        const facetColumns = getFacetHeaders(headers);
        if (facetColumns.length === 0) return [];

        const pairsSet = new Set();
        const categoriesSet = new Set(); // Track unique categories for Root Category option
        const sanitize = value => {
            if (value === null || value === undefined) return '(Blank)';
            const cleaned = String(value).replace(/<[^>]*>?/gm, '').trim();
            return cleaned === '' ? '(Blank)' : cleaned;
        };

        // DEBUG: Check for Anti Climb Paint in input data
        console.log('[DEBUG FRONTEND] Total rows in data:', data.length);
        if (data.length > 0) {
            console.log('[DEBUG FRONTEND] First row keys:', Object.keys(data[0]));
            console.log('[DEBUG FRONTEND] First row sample:', JSON.stringify(data[0], null, 2).substring(0, 500));
        }
        
        // Check all possible category field names
        const categoryFields = ['Category Mapping', 'CategoryMapping', 'category_mapping', 'Category'];
        let categoryField = null;
        for (const field of categoryFields) {
            if (data.length > 0 && data[0].hasOwnProperty(field)) {
                categoryField = field;
                console.log(`[DEBUG FRONTEND] Found category field: "${field}"`);
                break;
            }
        }
        
        // Also check if any row has "climb" in any field
        const climbRows = data.filter(row => {
            if (!row) return false;
            for (const key in row) {
                const value = String(row[key] || '').toLowerCase();
                if (value.includes('climb')) {
                    console.log(`[DEBUG FRONTEND] Found "climb" in field "${key}": "${row[key]}"`);
                    return true;
                }
            }
            return false;
        });
        
        if (climbRows.length > 0) {
            console.log('[DEBUG FRONTEND] Found', climbRows.length, 'rows with "climb" anywhere:');
            climbRows.slice(0, 3).forEach((row, idx) => {
                console.log(`  [${idx}] Full row:`, JSON.stringify(row, null, 2).substring(0, 1000));
                console.log(`  [${idx}] Category Mapping: "${row['Category Mapping']}"`);
                console.log(`  [${idx}] Navigation_Type: "${row['Navigation_Type']}"`);
                console.log(`  [${idx}] All facet fields:`, Object.keys(row).filter(k => k !== 'Category Mapping' && k !== 'Monthly Organic Traffic' && k !== 'Total Monthly Google Searches' && k !== 'Total On-Site Searches' && k !== 'KeywordDetails'));
            });
        } else {
            console.log('[DEBUG FRONTEND] WARNING: No rows found with "climb" anywhere!');
            console.log('[DEBUG FRONTEND] Sample categories in data:', data.slice(0, 10).map(r => {
                const cat = categoryField ? r[categoryField] : r['Category Mapping'];
                return cat;
            }).filter(Boolean));
        }

        // Use detected category field or fallback to 'Category Mapping'
        const catField = categoryField || 'Category Mapping';
        
        // DEBUG: Search for "Anti Climb Paint" specifically in Category Mapping
        const antiClimbPaintRows = data.filter(row => {
            const cat = String(row[catField] || '').toLowerCase();
            return cat.includes('anti') && cat.includes('climb') && cat.includes('paint');
        });
        if (antiClimbPaintRows.length > 0) {
            console.log(`[DEBUG FRONTEND] Found ${antiClimbPaintRows.length} rows with "Anti Climb Paint" in Category Mapping:`);
            antiClimbPaintRows.slice(0, 2).forEach((row, idx) => {
                console.log(`  [${idx}] Category Mapping: "${row[catField]}"`);
            });
        } else {
            console.log('[DEBUG FRONTEND] No rows found with "Anti Climb Paint" in Category Mapping');
            
            // Check ALL unique Category Mapping values to see what we have
            const allCategories = new Set();
            data.forEach(row => {
                const cat = String(row[catField] || '').trim();
                if (cat && cat !== '(Blank)') {
                    allCategories.add(cat);
                }
            });
            console.log(`[DEBUG FRONTEND] Total unique categories in Category Mapping: ${allCategories.size}`);
            
            // Check for categories containing "climb"
            const climbCategories = Array.from(allCategories).filter(cat => cat.toLowerCase().includes('climb'));
            if (climbCategories.length > 0) {
                console.log(`[DEBUG FRONTEND] Categories with "climb": ${climbCategories.join(', ')}`);
            }
            
            // Check if we need to construct category from Category Mapping + Navigation_Type
            const constructedRows = data.filter(row => {
                const navType = String(row['Navigation_Type'] || '').toLowerCase();
                return navType.includes('anti') && navType.includes('climb');
            });
            if (constructedRows.length > 0) {
                console.log(`[DEBUG FRONTEND] Found ${constructedRows.length} rows with "Anti Climb" in Navigation_Type`);
                console.log(`[DEBUG FRONTEND] Sample: Category Mapping="${constructedRows[0][catField]}", Navigation_Type="${constructedRows[0]['Navigation_Type']}"`);
                console.log(`[DEBUG FRONTEND] Should we construct category as: "${constructedRows[0][catField]} ${constructedRows[0]['Navigation_Type']}"?`);
            }
        }
        
        // Helper function to construct full category name from generic Category Mapping + facets
        function constructCategoryName(row) {
            const baseCategory = String(row[catField] || '').trim();
            
            // If Category Mapping is generic (ends with .Cat),
            // construct the full category name from Navigation_Type + base category
            if (baseCategory.endsWith('.Cat')) {
                const navType = String(row['Navigation_Type'] || '').trim();
                if (navType) {
                    // Remove .Cat suffix and combine with Navigation_Type
                    // Example: "Paint.Cat" + "Anti Climb" -> "Anti Climb Paint"
                    const baseName = baseCategory.replace(/\.Cat$/, '');
                    const constructed = `${navType} ${baseName}`.trim();
                    return constructed;
                }
            }
            
            // Return original category name if not generic or no Navigation_Type
            return baseCategory;
        }
        
        data.forEach(row => {
            if (!row) return;
            
            // Construct category name (may combine Category Mapping + Navigation_Type)
            const rawCategory = constructCategoryName(row);
            const categoryValue = sanitize(rawCategory);
            
            // DEBUG: Log category construction for Anti Climb
            if (rawCategory && rawCategory.toLowerCase().includes('climb')) {
                const originalCat = String(row[catField] || '').trim();
                const navType = String(row['Navigation_Type'] || '').trim();
                console.log(`[DEBUG FRONTEND] Constructed category: "${categoryValue}" from Category Mapping="${originalCat}" + Navigation_Type="${navType}"`);
            }
            
            // Track this category for Root Category option
            if (categoryValue && categoryValue !== '(Blank)') {
                categoriesSet.add(categoryValue);
            }
            
            // Create category-facet pairs with Facet Attribute
            facetColumns.forEach(column => {
                const cellValue = row[column];
                if (cellValue === null || cellValue === undefined) return;
                const values = String(cellValue).split('|').map(v => v.trim()).filter(Boolean);
                values.forEach(value => {
                    if (!value) return;
                    const cleanValue = sanitize(value);
                    // Include Facet Attribute (column name) in the key
                    const key = JSON.stringify([categoryValue, column, cleanValue]);
                    if (!pairsSet.has(key)) {
                        pairsSet.add(key);
                    }
                });
            });
        });

        const pairs = Array.from(pairsSet).map(key => {
            const [category, facetAttribute, facetValue] = JSON.parse(key);
            return {
                'Category Mapping': category,
                'Facet Attribute': facetAttribute, // Column name like "Colour"
                'Facet Value': facetValue
            };
        });
        
        // Add "Root Category" option for each unique category
        // This allows SKUs to be counted against just the category, even without matching facets
        const climbCategories = Array.from(categoriesSet).filter(cat => cat && cat.toLowerCase().includes('climb'));
        if (climbCategories.length > 0) {
            console.log('[DEBUG FRONTEND] Categories with "climb" in categoriesSet:', climbCategories);
        } else {
            console.log('[DEBUG FRONTEND] WARNING: No categories with "climb" in categoriesSet!');
            console.log('[DEBUG FRONTEND] Total categories in set:', categoriesSet.size);
            console.log('[DEBUG FRONTEND] Sample categories:', Array.from(categoriesSet).slice(0, 10));
        }
        
        categoriesSet.forEach(category => {
            if (category && category !== '(Blank)') {
                pairs.push({
                    'Category Mapping': category,
                    'Facet Attribute': 'Root Category',
                    'Facet Value': 'Root Category'
                });
                if (category.toLowerCase().includes('climb')) {
                    console.log(`[DEBUG FRONTEND] Added Root Category pair for: "${category}"`);
                }
            }
        });

        pairs.sort((a, b) => {
            const categoryCompare = a['Category Mapping'].localeCompare(b['Category Mapping']);
            if (categoryCompare !== 0) return categoryCompare;
            const attributeCompare = (a['Facet Attribute'] || '').localeCompare(b['Facet Attribute'] || '');
            if (attributeCompare !== 0) return attributeCompare;
            return (a['Facet Value'] || '').localeCompare(b['Facet Value'] || '');
        });

        // DEBUG: Check final pairs for Anti Climb Paint
        const climbPairs = pairs.filter(p => p['Category Mapping'] && p['Category Mapping'].toLowerCase().includes('climb'));
        if (climbPairs.length > 0) {
            console.log(`[DEBUG FRONTEND] Final pairs with "climb": ${climbPairs.length}`);
            climbPairs.forEach(p => {
                console.log(`  - "${p['Category Mapping']}" | ${p['Facet Attribute']} | ${p['Facet Value']}`);
            });
        } else {
            console.log('[DEBUG FRONTEND] WARNING: No pairs with "climb" in final output!');
            console.log('[DEBUG FRONTEND] Total pairs:', pairs.length);
        }

        return pairs;
    }

    async function addColoredConsolidationSheetToWorkbook(workbook, categoryConsolidationData) {
        const worksheet = workbook.addWorksheet('Category Consolidation');
        
        // Remove _facetPercentages from display data
        const cleanData = categoryConsolidationData.map(row => {
            const { _facetPercentages, ...cleanRow } = row;
            return cleanRow;
        });
        
        const allHeaders = Object.keys(cleanData[0] || {});
        const facetStartIndex = allHeaders.findIndex(h => 
            !h.includes('Category Mapping') && 
            !h.includes('Traffic') && 
            !h.includes('Searches')
        );
        
        // Helper function to get color based on percentage
        const getColorForPercentage = (percentage) => {
            if (percentage >= 75) return { argb: 'FF27AE60' }; // Green (75-100%) - Highest priority
            if (percentage >= 50) return { argb: 'FF82E0AA' }; // Light Green (50-75%) - High priority
            if (percentage >= 25) return { argb: 'FFFFD93D' }; // Yellow (25-50%) - Medium priority
            if (percentage >= 10) return { argb: 'FFFFA07A' }; // Light Coral (10-25%) - Low priority
            return { argb: 'FFFF6B6B' }; // Red (<10%) - Lowest priority
        };
        
        // Set up columns first (without adding header row yet)
        worksheet.columns = allHeaders.map(h => {
            let width = 15;
            if (h === 'Category Mapping') width = 25;
            else if (h.includes('Traffic') || h.includes('Searches')) width = 20;
            else width = 40;
            return { header: '', key: h, width }; // Empty header - we'll add it manually
        });
        
        // Add legend row at position 1
        const legendRow = worksheet.getRow(1);
        legendRow.values = ['LEGEND: Facet columns color-coded by traffic contribution % - 🟢 Green: 75-100% (Highest) | 🟢 Light Green: 50-75% | 🟡 Yellow: 25-50% | 🟠 Coral: 10-25% | 🔴 Red: <10% (Lowest). Facet values within each cell are ordered by traffic (highest first).'];
        legendRow.height = 40;
        legendRow.font = { bold: true, size: 11 };
        legendRow.fill = {
            type: 'pattern',
            pattern: 'solid',
            fgColor: { argb: 'FFE8F5E9' }
        };
        legendRow.alignment = { wrapText: true, vertical: 'middle', horizontal: 'left' };
        worksheet.mergeCells(1, 1, 1, allHeaders.length);
        
        // Add empty row at position 2
        worksheet.getRow(2).values = [];
        
        // Add header row at position 3
        const headerRow = worksheet.getRow(3);
        headerRow.values = allHeaders;
        headerRow.font = { bold: true };
        headerRow.fill = {
            type: 'pattern',
            pattern: 'solid',
            fgColor: { argb: 'FFD3D3D3' }
        };
        
        // Get PIM results if available for strikethrough
        const pimResults = window.pimAnalysisResults || null;

        // Add data rows starting from row 4 with coloring
        cleanData.forEach((dataRow, rowIndex) => {
            const rowNumber = rowIndex + 4; // Start at row 4
            const excelRow = worksheet.getRow(rowNumber);
            
            // Set values for this row
            const rowValues = [];
            allHeaders.forEach(header => {
                rowValues.push(dataRow[header] || '');
            });
            excelRow.values = rowValues;
            
            const originalRow = categoryConsolidationData[rowIndex];
            const category = dataRow['Category Mapping'] || '';
            
            // Apply coloring to facet columns
            if (facetStartIndex >= 0 && originalRow._facetPercentages) {
                allHeaders.forEach((header, colIndex) => {
                    if (colIndex >= facetStartIndex && originalRow._facetPercentages[header] !== undefined) {
                        const cell = excelRow.getCell(colIndex + 1);
                        const cellValue = dataRow[header];

                        if (cellValue === null || cellValue === undefined || String(cellValue).trim() === '') {
                            cell.fill = {
                                type: 'pattern',
                                pattern: 'solid',
                                fgColor: { argb: 'FF000000' }
                            };
                            cell.font = { color: { argb: 'FFFFFFFF' } };
                        } else {
                            const percentage = originalRow._facetPercentages[header];
                            const bgColor = getColorForPercentage(percentage);
                            
                            // Check if this facet value has SKUs - if not, strikethrough
                            let hasSkus = null;
                            if (pimResults && category) {
                                // Split cell value into individual facet values
                                const facetValues = String(cellValue).split('|').map(v => v.trim()).filter(Boolean);
                                // Check if any facet value has SKUs - must match Facet Attribute (column name)
                                // Use 'header' as the facet attribute (column name)
                                hasSkus = facetValues.some(facetValue => 
                                    hasSkusForCategoryFacet(category, facetValue, pimResults, header) === true
                                );
                            }
                            
                            cell.fill = {
                                type: 'pattern',
                                pattern: 'solid',
                                fgColor: bgColor
                            };
                            
                            // Set font color (no strikethrough)
                            cell.font = { color: { argb: 'FF000000' } };
                        }
                        cell.alignment = { wrapText: true, vertical: 'top' };
                    }
                });
            }
        });
    }

    function createCategoryConsolidationView(data, headers) {
        /**
         * Creates a consolidated view where each category mapping appears once,
         * with all unique facet values aggregated across all facet columns.
         * This helps users understand what values need to be collected for each category.
         */
        
        // Identify facet columns (exclude metrics, special columns, and KeywordDetails)
        const excludedColumns = [
            'Category Mapping',
            'Monthly Organic Traffic',
            'Annual Organic Traffic',
            'Total Monthly Google Searches',
            'Total Annual Google Searches',
            'Total On-Site Searches',
            'Keyword Count',
            'KeywordDetails',
            'Derived Facets',
            'Category & Facet Key',
            'Calculated SKU Count',
            'Recommendation'
        ];
        
        const facetColumns = headers.filter(h => 
            h && h.trim() !== '' && 
            !excludedColumns.includes(h) &&
            !h.includes('Traffic') &&
            !h.includes('Searches') &&
            !h.includes('Score') &&
            !h.includes('Count')
        );
        
        // Identify metric columns to aggregate
        const metricColumns = [
            'Monthly Organic Traffic',
            'Annual Organic Traffic',
            'Total Monthly Google Searches',
            'Total Annual Google Searches',
            'Total On-Site Searches',
            'Calculated SKU Count',
            'Recommendation'
        ].filter(col => headers.includes(col));
        
        // Determine primary traffic column for percentage calculations
        const primaryTrafficCol = metricColumns.find(col => col.includes('Traffic')) || metricColumns[0];
        
        // Group data by Category Mapping
        const categoryGroups = {};
        
        data.forEach(row => {
            const categoryMapping = row['Category Mapping'];
            if (!categoryMapping) return;
            
            if (!categoryGroups[categoryMapping]) {
                categoryGroups[categoryMapping] = {
                    categoryMapping: categoryMapping,
                    facetValues: {},
                    metrics: {},
                    facetTraffic: {}, // Track traffic contribution per facet column
                    facetValueTraffic: {} // Track traffic per individual facet value
                };
                
                // Initialize sets and maps for each facet column
                facetColumns.forEach(col => {
                    categoryGroups[categoryMapping].facetValues[col] = new Set();
                    categoryGroups[categoryMapping].facetTraffic[col] = 0;
                    categoryGroups[categoryMapping].facetValueTraffic[col] = {}; // Map of value -> traffic
                });
                
                // Initialize metric totals
                metricColumns.forEach(col => {
                    categoryGroups[categoryMapping].metrics[col] = 0;
                });
            }
            
            // Collect all unique facet values for this category
            facetColumns.forEach(col => {
                const value = row[col];
                if (value && String(value).trim() !== '') {
                    // Remove HTML tags if present
                    const cleanValue = typeof value === 'string' ? 
                        String(value).replace(/<[^>]*>?/gm, '').trim() : 
                        String(value).trim();
                    
                    if (cleanValue) {
                        categoryGroups[categoryMapping].facetValues[col].add(cleanValue);
                        
                        // Track traffic for rows that have this facet populated
                        const trafficValue = row[primaryTrafficCol];
                        if (trafficValue && !isNaN(trafficValue)) {
                            const traffic = Number(trafficValue);
                            categoryGroups[categoryMapping].facetTraffic[col] += traffic;
                            
                            // Track traffic per individual facet value
                            if (!categoryGroups[categoryMapping].facetValueTraffic[col][cleanValue]) {
                                categoryGroups[categoryMapping].facetValueTraffic[col][cleanValue] = 0;
                            }
                            categoryGroups[categoryMapping].facetValueTraffic[col][cleanValue] += traffic;
                        }
                    }
                }
            });
            
            // Aggregate metrics
            metricColumns.forEach(col => {
                const value = row[col];
                // For numeric columns, sum them
                if (col === 'Calculated SKU Count' || col === 'Recommendation') {
                    // For SKU Count and Recommendation, take the first non-null value
                    // (these should be consistent across rows for the same category)
                    if (value && categoryGroups[categoryMapping].metrics[col] === 0) {
                        categoryGroups[categoryMapping].metrics[col] = value;
                    }
                } else if (value && !isNaN(value)) {
                    categoryGroups[categoryMapping].metrics[col] += Number(value);
                }
            });
        });
        
        // Convert to array format for Excel
        const consolidatedData = Object.values(categoryGroups).map(group => {
            const row = {
                'Category Mapping': group.categoryMapping,
                _facetPercentages: {} // Store percentages for formatting (not displayed as column)
            };
            
            // Add aggregated metrics first (before facets for better visibility)
            metricColumns.forEach(col => {
                row[col] = group.metrics[col];
            });
            
            // Calculate traffic percentages for each facet
            const totalTraffic = group.metrics[primaryTrafficCol] || 0;
            
            // Add each facet column with its unique values (comma-separated, sorted by traffic)
            facetColumns.forEach(col => {
                const values = Array.from(group.facetValues[col]);
                
                // Sort values by traffic (highest first), then alphabetically as tiebreaker
                const sortedValues = values.sort((a, b) => {
                    const trafficA = group.facetValueTraffic[col][a] || 0;
                    const trafficB = group.facetValueTraffic[col][b] || 0;
                    if (trafficB !== trafficA) {
                        return trafficB - trafficA; // Descending by traffic
                    }
                    return a.localeCompare(b); // Alphabetical tiebreaker
                });
                
                row[col] = sortedValues.length > 0 ? sortedValues.join(', ') : '';
                
                // Calculate percentage of traffic associated with this facet
                if (totalTraffic > 0) {
                    row._facetPercentages[col] = (group.facetTraffic[col] / totalTraffic) * 100;
                } else {
                    row._facetPercentages[col] = 0;
                }
            });
            
            return row;
        });
        
        // Sort by traffic/searches (highest first), then alphabetically by category
        consolidatedData.sort((a, b) => {
            // Try to sort by traffic metrics (highest first)
            const trafficColA = metricColumns.find(col => col.includes('Traffic'));
            if (trafficColA) {
                const trafficDiff = (b[trafficColA] || 0) - (a[trafficColA] || 0);
                if (trafficDiff !== 0) return trafficDiff;
            }
            
            // If traffic is equal or not available, sort by searches
            const searchesColA = metricColumns.find(col => col.includes('Searches'));
            if (searchesColA) {
                const searchesDiff = (b[searchesColA] || 0) - (a[searchesColA] || 0);
                if (searchesDiff !== 0) return searchesDiff;
            }
            
            // Fall back to alphabetical sorting
            const catA = String(a['Category Mapping']).toLowerCase();
            const catB = String(b['Category Mapping']).toLowerCase();
            return catA.localeCompare(catB);
        });
        
        return consolidatedData;
    }

    function exportFacetPotentialToExcel(data, headers, fileName) {
        const wb = XLSX.utils.book_new();
        const topLevelHeaders = headers.filter(h => h !== ''); 
        const topLevelData = data.map(row => {
            const newRow = {};
            topLevelHeaders.forEach(header => {
                const rawValue = row[header];
                newRow[header] = typeof rawValue === 'string' ? String(rawValue).replace(/<[^>]*>?/gm, '') : rawValue;
            });
            return newRow;
        });
        const ws1 = XLSX.utils.json_to_sheet(topLevelData, { header: topLevelHeaders });
        XLSX.utils.book_append_sheet(wb, ws1, "Facet Potential Summary");

        const valueBreakdownData = [];
        const annualSuffix = tableState.timeframe === 'annual' ? 'Annual' : 'Monthly';

        data.forEach(parentRow => {
            if (parentRow.FacetValueDetails && parentRow.FacetValueDetails.length > 0) {
                parentRow.FacetValueDetails.forEach(detailRow => {
                    const newBreakdownRow = {
                        'Category Mapping': parentRow['Category Mapping'],
                        'Facet Type': parentRow['Facet Type'],
                        'Facet Value': detailRow['Facet Value'],
                        'Keyword Count': detailRow['Keyword Count'],
                        [`${annualSuffix} Organic Traffic`]: detailRow[`${annualSuffix} Organic Traffic`] || detailRow['Monthly Organic Traffic'] || 0,
                        [`Total ${annualSuffix} Google Searches`]: detailRow[`Total ${annualSuffix} Google Searches`] || detailRow['Total Monthly Google Searches'] || 0,
                    };
                    if (detailRow.hasOwnProperty('Total On-Site Searches')) {
                        newBreakdownRow['Total On-Site Searches'] = detailRow['Total On-Site Searches'];
                    }
                     if (detailRow.hasOwnProperty('Total Annual On-Site Searches')) {
                        newBreakdownRow['Total Annual On-Site Searches'] = detailRow['Total Annual On-Site Searches'];
                    }
                    valueBreakdownData.push(newBreakdownRow);
                });
            }
        });

        if (valueBreakdownData.length > 0) {
            const ws2 = XLSX.utils.json_to_sheet(valueBreakdownData);
            XLSX.utils.book_append_sheet(wb, ws2, "Facet Value Breakdown");
        }

        XLSX.writeFile(wb, `${fileName}.xlsx`);
    }

    function exportToExcel(data, headers, fileName) {
        const exportHeaders = headers.filter(h => h !== '');
        const cleanData = data.map(row => {
            const newRow = {};
            exportHeaders.forEach(header => {
                let rawValue = row[header];
                if (Array.isArray(rawValue)) {
                    rawValue = `${rawValue[0].toFixed(1)}% (${(rawValue[1] || 0).toLocaleString()})`;
                }
                const cleanValue = typeof rawValue === 'string' ? String(rawValue).replace(/<[^>]*>?/gm, '') : rawValue;
                newRow[header] = cleanValue;
            });
            return newRow;
        });
        const ws = XLSX.utils.json_to_sheet(cleanData, { header: exportHeaders });
        const wb = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(wb, ws, "Report");
        XLSX.writeFile(wb, `${fileName}.xlsx`);
    }

    function buildContentGapExport(data, headers, title) {
        const exportHeaders = [...headers.filter(h => h !== '')];
        const exportData = data.map(row => ({ ...row }));
        const skuCounts = window.contentGapSkuCounts || contentGapSkuCounts;
        const groupSkuIds = window.contentGapGroupSkuIds || contentGapGroupSkuIds || {};
        const groupKeywordsMap = buildContentGapGroupKeywordsMap();
        const isKeywordView = title.includes('Content Gaps | Individual Keywords');
        const isGroupView = title.includes('Content Gaps | Keyword Groups');

        if (!skuCounts || (!isKeywordView && !isGroupView)) {
            return { exportHeaders, exportData };
        }

        const addHeaderIfMissing = (h) => {
            if (!exportHeaders.includes(h)) exportHeaders.push(h);
        };

        if (isKeywordView) {
            addHeaderIfMissing('Estimated TS SKU Count');
            addHeaderIfMissing('Matched SKU IDs');
            exportData.forEach(row => {
                const kw = row['Keyword'];
                const entry = kw ? skuCounts[kw] : null;
                const countVal = entry && typeof entry === 'object'
                    ? (entry.count ?? entry.sku_count ?? entry.skuCount ?? 0)
                    : (entry ?? 0);
                const ids = entry && typeof entry === 'object' && Array.isArray(entry.sku_ids)
                    ? entry.sku_ids.filter(id => id !== null && id !== undefined && String(id).trim() !== '')
                    : [];
                row['Estimated TS SKU Count'] = countVal;
                row['Matched SKU IDs'] = ids.length ? ids.map(id => `${id} (${kw})`).join(', ') : '';
            });
        } else if (isGroupView) {
            addHeaderIfMissing('Estimated TS SKU Count');
            addHeaderIfMissing('Matched SKU IDs');
            addHeaderIfMissing('Group Keywords');
            exportData.forEach(row => {
                const groupName = row['Keyword Group'];
                const ids = groupSkuIds[groupName] || [];
                const kwMap = (window.contentGapGroupSkuIdKeywordMap || contentGapGroupSkuIdKeywordMap || {})[groupName] || {};
                const formatted = ids.map(id => {
                    const kw = kwMap[id];
                    return kw ? `${id} (${kw})` : id;
                });
                row['Matched SKU IDs'] = formatted.length ? formatted.join(', ') : '';
                const groupKeywords = groupKeywordsMap[groupName] || [];
                row['Group Keywords'] = groupKeywords.join(', ');
            });
        }

        return { exportHeaders, exportData };
    }

    function buildContentGapGroupKeywordsMap() {
        const map = {};
        const sources = [
            { report: analysisResults.topicGapReport || [], kwMap: analysisResults.topicKeywordMap || {} },
            { report: analysisResults.coreTopicGapReport || [], kwMap: analysisResults.coreTopicKeywordMap || {} }
        ];

        sources.forEach(src => {
            (src.report || []).forEach(row => {
                const groupName = row['Keyword Group'];
                const topicId = row['TopicID'];
                const keywords = src.kwMap ? src.kwMap[topicId] || [] : [];
                if (!groupName) return;
                if (!map[groupName]) map[groupName] = new Set();
                keywords.forEach(kw => map[groupName].add(kw));
            });
        });

        return Object.fromEntries(Object.entries(map).map(([k, v]) => [k, Array.from(v)]));
    }

    function exportToPdf(data, headers, fileName, title) {
        const { jsPDF } = window.jspdf;
        const doc = new jsPDF({ orientation: 'landscape' });
        const exportHeaders = headers.filter(h => h !== ''); 
        const body = data.map(row => exportHeaders.map(header => {
            let rawValue = row[header];
            if (Array.isArray(rawValue)) {
                rawValue = `${rawValue[0].toFixed(1)}% (${(rawValue[1] || 0).toLocaleString()})`;
            }
            return typeof rawValue === 'string' ? String(rawValue).replace(/<[^>]*>?/gm, '') : rawValue;
        }));
        doc.text(title, 14, 15);
        window.jspdf.plugin.autotable.default(doc, {
            head: [exportHeaders], body: body, startY: 20, theme: 'striped',
            headStyles: { fillColor: [22, 160, 133] },
            styles: { fontSize: 8, cellPadding: 2 },
            columnStyles: { text: { cellWidth: 'auto' } }
        });
        doc.save(`${fileName}.pdf`);
    }

    function exportCategoryOverhaulToJson(data, headers, fileName) {
        // Create a comprehensive JSON export with all nested data
        const exportData = {
            metadata: {
                exportType: "Category Overhaul Matrix",
                exportDate: new Date().toISOString(),
                timeframe: tableState.timeframe,
                totalRows: data.length,
                columns: headers.filter(h => h !== '')
            },
            summary: {
                totalTraffic: data.reduce((sum, row) => sum + (row['Monthly Organic Traffic'] || 0), 0),
                totalSearches: data.reduce((sum, row) => sum + (row['Total Monthly Google Searches'] || 0), 0),
                totalKeywords: data.reduce((sum, row) => sum + (row.KeywordDetails ? row.KeywordDetails.length : 0), 0)
            },
            matrix: data.map(row => {
                const cleanRow = {};
                headers.forEach(header => {
                    if (header !== '' && header !== 'KeywordDetails') {
                        let value = row[header];
                        // Clean HTML from values
                        if (typeof value === 'string') {
                            value = value.replace(/<[^>]*>?/gm, '');
                        }
                        cleanRow[header] = value;
                    }
                });
                
                // Add keyword details if they exist
                if (row.KeywordDetails && row.KeywordDetails.length > 0) {
                    cleanRow.keywordDetails = row.KeywordDetails.map(kw => ({
                        keyword: kw.Keyword || '',
                        monthlyGoogleSearches: kw['Monthly Google Searches'] || 0,
                        onSiteSearches: kw['On-Site Searches'] || 0,
                        monthlyOrganicTraffic: kw['Monthly Organic Traffic'] || 0,
                        topRankingCompetitor: kw['Top Ranking Competitor'] || '',
                        rank: kw.Rank || '',
                        url: kw.URL || ''
                    }));
                } else {
                    cleanRow.keywordDetails = [];
                }
                
                return cleanRow;
            })
        };

        // Create and download the JSON file
        const jsonString = JSON.stringify(exportData, null, 2);
        const blob = new Blob([jsonString], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${fileName}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    function exportFacetPotentialToJson(data, headers, fileName) {
        // Create a comprehensive JSON export with all nested data
        const exportData = {
            metadata: {
                exportType: "Facet Potential Analysis",
                exportDate: new Date().toISOString(),
                timeframe: tableState.timeframe,
                totalRows: data.length,
                columns: headers.filter(h => h !== '')
            },
            summary: {
                totalTraffic: data.reduce((sum, row) => sum + (row['Monthly Organic Traffic'] || 0), 0),
                totalSearches: data.reduce((sum, row) => sum + (row['Total Monthly Google Searches'] || 0), 0),
                totalKeywords: data.reduce((sum, row) => sum + (row['Keyword Count'] || 0), 0)
            },
            facetAnalysis: data.map(row => {
                const cleanRow = {};
                headers.forEach(header => {
                    if (header !== '' && header !== 'FacetValueDetails') {
                        let value = row[header];
                        // Clean HTML from values
                        if (typeof value === 'string') {
                            value = value.replace(/<[^>]*>?/gm, '');
                        }
                        cleanRow[header] = value;
                    }
                });
                
                // Add facet value details if they exist
                if (row.FacetValueDetails && row.FacetValueDetails.length > 0) {
                    cleanRow.facetValueDetails = row.FacetValueDetails.map(detail => ({
                        facetValue: detail['Facet Value'] || '',
                        keywordCount: detail['Keyword Count'] || 0,
                        monthlyOrganicTraffic: detail['Monthly Organic Traffic'] || 0,
                        totalMonthlyGoogleSearches: detail['Total Monthly Google Searches'] || 0,
                        totalOnSiteSearches: detail['Total On-Site Searches'] || 0
                    }));
                } else {
                    cleanRow.facetValueDetails = [];
                }
                
                return cleanRow;
            })
        };

        // Create and download the JSON file
        const jsonString = JSON.stringify(exportData, null, 2);
        const blob = new Blob([jsonString], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${fileName}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    function exportToJson(data, headers, fileName, title) {
        // Create a comprehensive JSON export for general reports
        const exportData = {
            metadata: {
                exportType: title,
                exportDate: new Date().toISOString(),
                timeframe: tableState.timeframe,
                totalRows: data.length,
                columns: headers.filter(h => h !== '')
            },
            summary: {
                totalTraffic: data.reduce((sum, row) => {
                    const trafficCol = headers.find(h => h.includes('Organic Traffic'));
                    return sum + (row[trafficCol] || 0);
                }, 0),
                totalSearches: data.reduce((sum, row) => {
                    const searchCol = headers.find(h => h.includes('Google Searches'));
                    return sum + (row[searchCol] || 0);
                }, 0)
            },
            data: data.map(row => {
                const cleanRow = {};
                headers.forEach(header => {
                    if (header !== '') {
                        let value = row[header];
                        // Clean HTML from values
                        if (typeof value === 'string') {
                            value = value.replace(/<[^>]*>?/gm, '');
                        }
                        // Handle market share arrays
                        if (Array.isArray(value)) {
                            value = {
                                percentage: value[0],
                                traffic: value[1]
                            };
                        }
                        cleanRow[header] = value;
                    }
                });
                return cleanRow;
            })
        };

        // Create and download the JSON file
        const jsonString = JSON.stringify(exportData, null, 2);
        const blob = new Blob([jsonString], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${fileName}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    function openKeywordModal(topicID, mapSource) {
        let keywords = [];
        let modalTitleText = '';
        let map, reportData, reportRow, idKey;

        switch(mapSource) {
            case 'topic-threats':
                map = analysisResults.topicThreatsKeywordMap; reportData = analysisResults.topicThreatsReport; idKey = 'TopicID'; break;
            case 'core-threats':
                map = analysisResults.coreTopicThreatsKeywordMap; reportData = analysisResults.coreTopicThreatsReport; idKey = 'TopicID'; break;
            case 'core':
                map = analysisResults.coreTopicKeywordMap; reportData = analysisResults.coreTopicGapReport; idKey = 'TopicID'; break;
            case 'full':
                map = analysisResults.topicKeywordMap; reportData = analysisResults.topicGapReport; idKey = 'TopicID'; break;
            case 'market-share-group':
                map = analysisResults.groupMarketShareKeywordMap; reportData = analysisResults.groupMarketShareReport; idKey = 'Keyword Group'; break;
            case 'market-share-core-group':
                map = analysisResults.coreGroupMarketShareKeywordMap; reportData = analysisResults.coreGroupMarketShareReport; idKey = 'Keyword Group'; break;
        }

        if (map && reportData) {
            keywords = map[topicID] || [];
            reportRow = reportData.find(row => row[idKey] === topicID);
            modalTitleText = reportRow ? `Keywords in "${reportRow['Keyword Group']}"` : `Keywords`;
        }
        
        ui.modalTitle.textContent = modalTitleText;
        ui.modalKeywordList.innerHTML = keywords.length > 0
            ? keywords.map(kw => `<div class="keyword-list-item">${kw}</div>`).join('')
            : '<div class="text-gray-500">No keywords found for this group.</div>';
        ui.keywordModal.classList.remove('hidden');
    }

    function closeKeywordModal() {
        ui.keywordModal.classList.add('hidden');
    }

    function updateFileLabel(input) {
        const label = input.previousElementSibling;
        if (input.files.length > 0) { label.classList.add('has-file'); label.querySelector('span').textContent = `${input.files.length} file(s) selected`; }
    }

    function checkCanAnalyse() {
        const allRequiredMapped = ['keywordCol', 'urlCol', 'positionCol'].every(id => document.getElementById(id) && document.getElementById(id).value !== '');
        const ourFileReady = document.getElementById('our-file') && document.getElementById('our-file').files.length > 0;
        const compFilesReady = document.getElementById('competitor-files') && document.getElementById('competitor-files').files.length > 0;
        
        const analyseBtn = document.getElementById('analyse-btn');
        if (analyseBtn) {
            analyseBtn.disabled = !(ourFileReady && compFilesReady && allRequiredMapped);
        }
    }

    function populateColumnMappers(headers) {
        console.log('populateColumnMappers called with headers:', headers);
        const colMap = { keywordCol: 'Keyword', urlCol: 'URL', positionCol: 'Position', volumeCol: 'Volume', trafficCol: 'Traffic' };
        let mapperHtml = '';
        Object.entries(colMap).forEach(([key, label]) => {
            const isRequired = ['keywordCol', 'urlCol', 'positionCol'].includes(key);
            const options = headers.map(h => `<option value="${h}">${h}</option>`).join('');
            mapperHtml += `
            <div class="flex items-center"> <div>
                    <label for="${key}" class="block text-sm font-medium">${label}${isRequired ? '*' : ''}</label>
                    <select id="${key}" name="${key}" class="mt-1 block w-full rounded-md border-gray-300">
                        <option value="">${isRequired ? 'Select*' : 'Optional'}</option>${options}
                    </select>
                </div>
                ${key === 'trafficCol' ? `
                    <div class="tooltip-container ml-2">
                        <svg class="tooltip-icon h-4 w-4 text-gray-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd" /></svg>
                        <span class="tooltip-text">Required for Market Share reports. If not mapped, these reports will not be generated.</span>
                    </div>
                ` : ''}
            </div>`;
        });
        document.getElementById('column-mappers').innerHTML = mapperHtml;
        headers.forEach(h => {
            const h_lower = h.toLowerCase();
            if(h_lower.includes('keyword')) document.getElementById('keywordCol').value = h;
            if(h_lower.includes('url')) document.getElementById('urlCol').value = h;
            if(h_lower.includes('position')) document.getElementById('positionCol').value = h;
            if(h_lower.includes('volume') || h_lower.includes('sv')) document.getElementById('volumeCol').value = h;
            if(h_lower.includes('traffic')) document.getElementById('trafficCol').value = h;
        });
        document.querySelectorAll('#column-mappers select').forEach(sel => sel.addEventListener('change', checkCanAnalyse));
        checkCanAnalyse();
    }

    function renderOverridesUI(headers) {
        const container = document.getElementById('manual-overrides-container');
        if (!container) return;

        const filteredHeaders = headers.filter(h => !h.includes('Traffic') && !h.includes('Searches'));
        const optionsHtml = filteredHeaders.map(h => `<option value="${h}">${h}</option>`).join('');

        const activeRulesHtml = overrideRules.map(rule => {
            let ruleText = `From <b>${rule.sourceColumn}</b>, `;
            if (rule.action === 'delete') {
                ruleText += `delete & merge value "<b>${rule.value}</b>"`;
            } else if (rule.action === 'remove') {
                ruleText += `delete & remove rows with value "<b>${rule.value}</b>" <span class="text-xs bg-red-100 text-red-800 px-2 py-0.5 rounded">(removes rows)</span>`;
            } else if (rule.action === 'move') {
                const targetDisplay = rule.isNew ? `new column "<b>${rule.targetColumn}</b>"` : `<b>${rule.targetColumn}</b>`;
                const modeDisplay = rule.moveMode === 'replace' ? ' <span class="text-xs bg-orange-100 text-orange-800 px-2 py-0.5 rounded">(replace)</span>' : ' <span class="text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded">(append)</span>';
                ruleText += `move value "<b>${rule.value}</b>" to ${targetDisplay}${modeDisplay}`;
            } else if (rule.action === 'change') {
                const valueDisplay = rule.value === '' ? '<em>(Blank)</em>' : `"${rule.value}"`;
                ruleText += `change value ${valueDisplay} to "<b>${rule.newValue}</b>"`;
            }
            if (rule.conditions && Object.keys(rule.conditions).length > 0) {
                const conditionsText = Object.entries(rule.conditions).map(([col, val]) => {
                    const displayVal = val === '' ? '<em>(Blank)</em>' : `"${val}"`;
                    return `${col} = ${displayVal}`;
                }).join(' AND ');
                ruleText += `<div class="text-xs text-gray-500 mt-1">Only when ${conditionsText}</div>`;
            }
            return `<li class="flex justify-between items-center p-2 border-b"><span>${ruleText}</span><button class="remove-rule-btn text-red-500 hover:text-red-700 font-bold" data-rule-id="${rule.id}">&times;</button></li>`;
        }).join('');

        container.innerHTML = `
            <div class="border rounded-lg p-4 bg-gray-50">
                <details>
                    <summary class="font-bold text-lg cursor-pointer">Manual Overrides</summary>
                    <div class="mt-4">
                        <div class="border-b border-gray-200">
                            <nav class="-mb-px flex space-x-8" aria-label="Tabs">
                                <button class="tab-btn whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm border-blue-500 text-blue-600" data-tab="value-rules">Value-Based Rules</button>
                                <button class="tab-btn whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300" data-tab="column-ops">Column Operations</button>
                            </nav>
                        </div>
                        <div class="mt-4">
                            <div id="value-rules-panel" class="tab-panel">
                                <div class="grid grid-cols-1 md:grid-cols-6 gap-4 items-end p-4 border rounded-md bg-white">
                                    <div class="md:col-span-1">
                                        <label for="rule-source-column" class="block text-sm font-medium">Column</label>
                                        <select id="rule-source-column" class="mt-1 block w-full p-2 border-gray-300 rounded-md">${optionsHtml}</select>
                                    </div>
                                    <div class="md:col-span-2">
                                        <label for="rule-value-filter" class="block text-sm font-medium">Values to Find (select one or more)</label>
                                        <input type="text" id="rule-value-filter" placeholder="Filter values..." class="mt-1 block w-full p-2 border-gray-300 rounded-md text-sm">
                                        <div class="flex justify-between items-center mt-1 px-1 text-xs">
                                            <a href="#" id="select-all-values-btn" class="text-blue-600 hover:underline font-semibold">Select All Visible</a>
                                            <a href="#" id="deselect-all-values-btn" class="text-blue-600 hover:underline font-semibold">Deselect All</a>
                                        </div>
                                        <div id="rule-value-listbox" class="mt-1 h-40 border rounded-md overflow-y-auto bg-white">
                                            <div class="p-2 text-gray-400 text-sm">Select a column first</div>
                                        </div>
                                    </div>
                                    <div class="md:col-span-1">
                                        <label for="rule-action" class="block text-sm font-medium">Action</label>
                                        <select id="rule-action" class="mt-1 block w-full p-2 border-gray-300 rounded-md">
                                            <option value="change">Change Value</option>
                                            <option value="delete">Delete & Merge</option>
                                            <option value="remove">Delete & Remove</option>
                                            <option value="move">Move Value</option>
                                        </select>
                                    </div>
                                    <div class="md:col-span-1">
                                        <div id="rule-target-container" class="space-y-2" style="display: none;">
                                            <label class="block text-sm font-medium">Move to Column</label>
                                            <select id="rule-target-column" class="block w-full p-2 border-gray-300 rounded-md">${optionsHtml}</select>
                                            <input type="text" id="new-column-name-input" placeholder="New column name..." class="hidden mt-1 block w-full p-2 border-gray-300 rounded-md">
                                            <div>
                                                <input type="checkbox" id="create-new-column-toggle" class="h-4 w-4 rounded border-gray-300">
                                                <label for="create-new-column-toggle" class="ml-2 text-sm">Create new column</label>
                                            </div>
                                            <div class="mt-2 pt-2 border-t border-gray-200">
                                                <label class="block text-sm font-medium mb-2">Move Mode</label>
                                                <div class="space-y-1">
                                                    <div>
                                                        <input type="radio" id="move-mode-append" name="move-mode" value="append" class="h-4 w-4" checked>
                                                        <label for="move-mode-append" class="ml-2 text-sm">Append (keep existing & add)</label>
                                                    </div>
                                                    <div>
                                                        <input type="radio" id="move-mode-replace" name="move-mode" value="replace" class="h-4 w-4">
                                                        <label for="move-mode-replace" class="ml-2 text-sm">Replace (overwrite existing)</label>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                        <div id="rule-new-value-container">
                                            <label for="rule-new-value" class="block text-sm font-medium">New Value</label>
                                            <input type="text" id="rule-new-value" class="mt-1 block w-full p-2 border-gray-300 rounded-md">
                                        </div>
                                    </div>
                                    <div class="md:col-span-1">
                                        <button id="add-rule-btn" class="w-full ts-button-primary px-4 py-2 rounded-lg control-btn" disabled>+ Add Rule(s)</button>
                                    </div>
                                </div>
                                <div class="mt-4">
                                    <div class="flex justify-between items-center mb-2">
                                        <div class="flex items-center gap-2">
                                            <h4 class="font-semibold">Active Rules</h4>
                                            ${overrideRules.length > 0 ? `<button id="toggle-active-rules-btn" class="text-xs text-blue-600 hover:underline" title="${isActiveRulesCollapsed ? 'Expand' : 'Collapse'}">${isActiveRulesCollapsed ? '▶' : '▼'}</button>` : ''}
                                        </div>
                                        ${overrideRules.length > 0 ? '<button id="clear-all-rules-btn" class="text-xs text-red-600 hover:underline">Clear All Rules</button>' : ''}
                                    </div>
                                    <ul id="active-rules-list" class="bg-white rounded-md border ${isActiveRulesCollapsed ? 'hidden' : ''}">${overrideRules.length > 0 ? activeRulesHtml : '<li class="p-3 text-gray-500 text-center">No active rules.</li>'}</ul>
                                </div>
                            </div>
                            <div id="column-ops-panel" class="tab-panel hidden">
                                <div class="grid grid-cols-1 md:grid-cols-3 gap-4 items-end p-4 border rounded-md bg-white">
                                    <div><label for="merge-source-column" class="block text-sm font-medium">Merge & Delete this Column</label><select id="merge-source-column" class="mt-1 block w-full p-2 border-gray-300 rounded-md">${optionsHtml}</select></div>
                                    <div><label for="merge-target-column" class="block text-sm font-medium">Into this Column</label><select id="merge-target-column" class="mt-1 block w-full p-2 border-gray-300 rounded-md">${optionsHtml}</select></div>
                                    <div><button id="merge-column-btn" class="w-full bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 control-btn">Merge & Delete</button></div>
                                </div>
                            </div>
                        </div>
                    </div>
                </details>
            </div>
        `;
        setupOverridesEventListeners();
    }

    function setupOverridesEventListeners() {
        const handleRuleChange = () => {
            const currentView = document.querySelector('[data-report-title]').dataset.reportTitle;
            if (currentView.includes('Category Overhaul Matrix')) renderCategoryOverhaulMatrixView();
            else if (currentView.includes('Facet Potential Analysis')) renderFacetPotentialAnalysisView();
        };
        
        const tabButtons = document.querySelectorAll('.tab-btn');
        const tabPanels = document.querySelectorAll('.tab-panel');
        tabButtons.forEach(button => {
            button.addEventListener('click', () => {
                tabButtons.forEach(btn => {
                    btn.classList.remove('border-blue-500', 'text-blue-600');
                    btn.classList.add('border-transparent', 'text-gray-500', 'hover:text-gray-700', 'hover:border-gray-300');
                });
                button.classList.add('border-blue-500', 'text-blue-600');
                button.classList.remove('border-transparent', 'text-gray-500');

                tabPanels.forEach(panel => panel.classList.add('hidden'));
                document.getElementById(button.dataset.tab + '-panel')?.classList.remove('hidden');
            });
        });

        // Toggle Active Rules expand/collapse
        const toggleActiveRulesBtn = document.getElementById('toggle-active-rules-btn');
        if (toggleActiveRulesBtn) {
            toggleActiveRulesBtn.addEventListener('click', () => {
                // Toggle the state variable
                isActiveRulesCollapsed = !isActiveRulesCollapsed;
                
                // Update the DOM immediately
                const activeRulesList = document.getElementById('active-rules-list');
                if (isActiveRulesCollapsed) {
                    activeRulesList.classList.add('hidden');
                    toggleActiveRulesBtn.textContent = '▶';
                    toggleActiveRulesBtn.title = 'Expand';
                } else {
                    activeRulesList.classList.remove('hidden');
                    toggleActiveRulesBtn.textContent = '▼';
                    toggleActiveRulesBtn.title = 'Collapse';
                }
            });
        }

        const populateValueListbox = () => {
            const sourceColumnSelect = document.getElementById('rule-source-column');
            const selectedColumn = sourceColumnSelect.value;
            const baseHeaders = Object.keys(analysisResults.categoryOverhaulMatrixReport[0] || {});
            const currentDataState = applyOverridesAndMerge(analysisResults.categoryOverhaulMatrixReport, baseHeaders, analysisResults.hasOnsiteData);
            
            // Get traffic headers for filtering
            const annualTrafficHeader = updateHeadersForTimeframe(['Monthly Organic Traffic'], 'annual')[0];
            const monthlyTrafficHeader = updateHeadersForTimeframe(['Monthly Organic Traffic'], 'monthly')[0];
            
            // If hideZeroTraffic is enabled, filter values that only appear on rows with 0 traffic
            const shouldFilterByTraffic = tableState.hideZeroTraffic;
            
            // Track which values appear on rows with traffic > 0
            const valueToRowMap = new Map(); // value -> array of rows containing this value
            
            currentDataState.forEach(row => {
                const cellValue = row[selectedColumn];
                const values = cellValue === null || cellValue === undefined || String(cellValue).trim() === '' 
                    ? [''] 
                    : String(cellValue).split(' | ').map(v => v.trim());
                
                values.forEach(v => {
                    if (!valueToRowMap.has(v)) {
                        valueToRowMap.set(v, []);
                    }
                    valueToRowMap.get(v).push(row);
                });
            });
            
            const valueSet = new Set();
            let hasBlanks = false;

            // Filter values based on traffic if hideZeroTraffic is enabled
            valueToRowMap.forEach((rows, value) => {
                if (value === '') {
                    hasBlanks = true;
                } else {
                    if (shouldFilterByTraffic) {
                        // Only include value if it appears on at least one row with traffic > 0
                        const hasTraffic = rows.some(row => {
                            const traffic = row[annualTrafficHeader] || row[monthlyTrafficHeader];
                            return typeof traffic === 'number' && traffic > 0;
                        });
                        if (hasTraffic) {
                            valueSet.add(value);
                        }
                    } else {
                        // Include all values if filtering is disabled
                        valueSet.add(value);
                    }
                }
            });
            
            // Handle blanks - only show if blank appears on at least one row with traffic > 0
            if (hasBlanks && shouldFilterByTraffic) {
                const blankRows = valueToRowMap.get('') || [];
                const blankHasTraffic = blankRows.some(row => {
                    const traffic = row[annualTrafficHeader] || row[monthlyTrafficHeader];
                    return typeof traffic === 'number' && traffic > 0;
                });
                if (!blankHasTraffic) {
                    hasBlanks = false; // Hide blank option if all blank rows have 0 traffic
                }
            }

            const sortedValues = Array.from(valueSet).sort();
            const listbox = document.getElementById('rule-value-listbox');
            const addRuleBtn = document.getElementById('add-rule-btn');
            
            let listboxItems = sortedValues.map(v => `<div class="rule-value-item p-2 text-sm cursor-pointer hover:bg-blue-50 border-b" data-value="${v}" tabindex="0">${v}</div>`).join('');
            
            if (hasBlanks) {
                const blankOptionHtml = `<div class="rule-value-item p-2 text-sm cursor-pointer hover:bg-blue-50 border-b" data-value="" tabindex="0"><em>(Blank)</em></div>`;
                listboxItems = blankOptionHtml + listboxItems;
            }

            if (listbox) {
                listbox.innerHTML = listboxItems || '<div class="p-2 text-gray-500 text-sm">No values found</div>';
                addRuleBtn.disabled = !listboxItems;
            }
        };
        
        document.getElementById('rule-source-column')?.addEventListener('change', populateValueListbox);
        
        document.getElementById('rule-action')?.addEventListener('change', (e) => {
            const action = e.target.value;
            document.getElementById('rule-target-container').style.display = action === 'move' ? 'block' : 'none';
            document.getElementById('rule-new-value-container').style.display = action === 'change' ? 'block' : 'none';
        });
        
        document.getElementById('create-new-column-toggle')?.addEventListener('change', (e) => {
            const isChecked = e.target.checked;
            document.getElementById('rule-target-column').classList.toggle('hidden', isChecked);
            document.getElementById('new-column-name-input').classList.toggle('hidden', !isChecked);
        });

        document.getElementById('add-rule-btn')?.addEventListener('click', () => {
            const sourceColumn = document.getElementById('rule-source-column').value;
            const action = document.getElementById('rule-action').value;
            const selectedItems = document.querySelectorAll('#rule-value-listbox .rule-value-item.selected');
            
            if (selectedItems.length === 0) {
                alert('Please select at least one value from the list.');
                return;
            }
            
            let targetColumn, newValue, isNew = false, moveMode = 'append';

            if (action === 'change') {
                newValue = document.getElementById('rule-new-value').value;
                if (!newValue.trim()) {
                    alert('Please enter a new value for the "Change" action.');
                    return;
                }
            } else if (action === 'move') {
                const isCreatingNew = document.getElementById('create-new-column-toggle').checked;
                if (isCreatingNew) {
                    targetColumn = document.getElementById('new-column-name-input').value.trim();
                    if (!targetColumn) {
                        alert('Please enter a name for the new column.');
                        return;
                    }
                    const currentHeaders = Object.keys(analysisResults.categoryOverhaulMatrixReport[0] || {});
                    if (currentHeaders.includes(targetColumn)) {
                        alert('A column with this name already exists.');
                        return;
                    }
                    isNew = true;
                    // Add the new column to the underlying data immediately
                    analysisResults.categoryOverhaulMatrixReport.forEach(row => row[targetColumn] = null);
                } else {
                    targetColumn = document.getElementById('rule-target-column').value;
                }
                
                // Capture the move mode (append or replace)
                const moveModeRadio = document.querySelector('input[name="move-mode"]:checked');
                moveMode = moveModeRadio ? moveModeRadio.value : 'append';
            }

            selectedItems.forEach(item => {
                const value = item.dataset.value;
                if (value === '' && (action === 'move' || action === 'delete' || action === 'remove')) return;
                overrideRules.push({ id: Date.now() + Math.random(), sourceColumn, value, action, targetColumn, newValue, isNew, moveMode });
            });

            handleRuleChange();
        });
        
        document.getElementById('active-rules-list')?.addEventListener('click', (e) => {
            if(e.target.matches('.remove-rule-btn')) {
                const ruleId = parseFloat(e.target.dataset.ruleId);
                overrideRules = overrideRules.filter(r => r.id !== ruleId);
                handleRuleChange();
            }
        });
        
        document.getElementById('clear-all-rules-btn')?.addEventListener('click', () => {
            overrideRules = [];
            isActiveRulesCollapsed = false; // Reset to expanded state when rules are cleared
            handleRuleChange();
        });

        document.getElementById('merge-column-btn')?.addEventListener('click', () => {
            const sourceCol = document.getElementById('merge-source-column').value;
            const targetCol = document.getElementById('merge-target-column').value;

            if (sourceCol === targetCol) {
                alert('Source and Target columns cannot be the same.');
                return;
            }

            if (confirm(`Are you sure you want to merge all values from "${sourceCol}" into "${targetCol}" and delete the "${sourceCol}" column? This action cannot be undone.`)) {
                analysisResults.categoryOverhaulMatrixReport.forEach(row => {
                    const sourceValue = row[sourceCol];
                    if (sourceValue !== null && sourceValue !== undefined && String(sourceValue).trim() !== '') {
                        const targetValue = row[targetCol];
                        const sourceValues = String(sourceValue).split(' | ').map(v => v.trim());
                        const targetValues = (!targetValue || String(targetValue).trim() === '') ? [] : String(targetValue).split(' | ').map(v => v.trim());
                        const combined = new Set([...targetValues, ...sourceValues]);
                        row[targetCol] = Array.from(combined).join(' | ');
                    }
                    delete row[sourceCol];
                });
                handleRuleChange(); 
            }
        });

        document.getElementById('rule-value-listbox')?.addEventListener('click', (e) => {
            const item = e.target.closest('.rule-value-item');
            if (item) {
                item.classList.toggle('selected');
            }
        });

        document.getElementById('rule-value-filter')?.addEventListener('input', (e) => {
            const filterText = e.target.value.toLowerCase();
            const items = document.querySelectorAll('#rule-value-listbox .rule-value-item');
            items.forEach(item => {
                const itemText = item.dataset.value.toLowerCase();
                item.style.display = itemText.includes(filterText) ? 'block' : 'none';
            });
        });

        document.getElementById('select-all-values-btn')?.addEventListener('click', (e) => {
            e.preventDefault();
            document.querySelectorAll('#rule-value-listbox .rule-value-item').forEach(item => {
                if (item.style.display !== 'none') {
                    item.classList.add('selected');
                }
            });
        });

        document.getElementById('deselect-all-values-btn')?.addEventListener('click', (e) => {
            e.preventDefault();
            document.querySelectorAll('#rule-value-listbox .rule-value-item.selected').forEach(item => {
                item.classList.remove('selected');
            });
        });

        if(document.getElementById('rule-source-column')) populateValueListbox();
    }
    
    function generateFacetPotentialFromMatrix(matrixData, baseHeaders, hasOnsite) {
        if (!matrixData || matrixData.length === 0) return [];
        
        const facetHeaders = baseHeaders.filter(h => 
            h !== 'Category Mapping' && !h.includes('Traffic') && !h.includes('Searches') && h !== 'KeywordDetails'
        );
        
        let meltedData = [];
        matrixData.forEach(row => {
            facetHeaders.forEach(facetType => {
                if (!row.hasOwnProperty(facetType)) return;
                const facetValue = row[facetType];
                if (facetValue !== null && facetValue !== undefined && String(facetValue).trim() !== '') {
                    const values = String(facetValue).split(' | ').map(v => v.trim());
                    values.forEach(val => {
                        let newRow = {
                            'Category Mapping': row['Category Mapping'],
                            'Facet Type': facetType,
                            'Facet Value': val,
                            'Monthly Organic Traffic': row['Monthly Organic Traffic'] || 0,
                            'Total Monthly Google Searches': row['Total Monthly Google Searches'] || 0,
                            'Keyword Count': row.KeywordDetails ? row.KeywordDetails.length : 0
                        };
                        if (hasOnsite) {
                            newRow['Total On-Site Searches'] = row['Total On-Site Searches'] || 0;
                        }
                        meltedData.push(newRow);
                    });
                }
            });
        });

        const aggregation = {};
        meltedData.forEach(row => {
            const key = `${row['Category Mapping']}||${row['Facet Type']}`;
            if (!aggregation[key]) {
                aggregation[key] = {
                    'Category Mapping': row['Category Mapping'],
                    'Facet Type': row['Facet Type'],
                    'Monthly Organic Traffic': 0,
                    'Total Monthly Google Searches': 0,
                    'Keyword Count': 0,
                     'FacetValueDetails': {}
                };
                if (hasOnsite) aggregation[key]['Total On-Site Searches'] = 0;
            }
            aggregation[key]['Monthly Organic Traffic'] += row['Monthly Organic Traffic'];
            aggregation[key]['Total Monthly Google Searches'] += row['Total Monthly Google Searches'];
            if(hasOnsite) aggregation[key]['Total On-Site Searches'] += row['Total On-Site Searches'];
            
            const detailKey = row['Facet Value'];
             if(!aggregation[key].FacetValueDetails[detailKey]) {
                 aggregation[key].FacetValueDetails[detailKey] = {
                     'Facet Value': detailKey, 'Monthly Organic Traffic': 0,
                     'Total Monthly Google Searches': 0, 'Keyword Count': 0,
                 };
                 if(hasOnsite) aggregation[key].FacetValueDetails[detailKey]['Total On-Site Searches'] = 0;
             }
             aggregation[key].FacetValueDetails[detailKey]['Monthly Organic Traffic'] += row['Monthly Organic Traffic'];
             aggregation[key].FacetValueDetails[detailKey]['Total Monthly Google Searches'] += row['Total Monthly Google Searches'];
             aggregation[key].FacetValueDetails[detailKey]['Keyword Count'] += row['Keyword Count'];
             aggregation[key]['Keyword Count'] += row['Keyword Count'];
             if(hasOnsite) aggregation[key].FacetValueDetails[detailKey]['Total On-Site Searches'] += row['Total On-Site Searches'];
        });
        
        let finalReport = Object.values(aggregation);
        
        const masterWeights = {
            'Monthly Organic Traffic': 0.34,
            'Total Monthly Google Searches': 0.33,
            'Total On-Site Searches': 0.33
        };
        const availableCols = Object.keys(masterWeights).filter(col => 
            finalReport.length > 0 && finalReport[0].hasOwnProperty(col)
        );

        if (availableCols.length > 0) {
            const totalWeightAvailable = availableCols.reduce((sum, col) => sum + masterWeights[col], 0);
            const dynamicWeights = {};
            availableCols.forEach(col => {
                dynamicWeights[col] = masterWeights[col] / totalWeightAvailable;
            });

            const minMax = {};
            availableCols.forEach(col => {
                const values = finalReport.map(row => row[col]);
                minMax[col] = { min: Math.min(...values), max: Math.max(...values) };
            });

            finalReport.forEach(row => {
                let score = 0;
                availableCols.forEach(col => {
                    const { min, max } = minMax[col];
                    const normalized = (max > min) ? (row[col] - min) / (max - min) : 0;
                    score += normalized * dynamicWeights[col];
                });
                
                let finalScore = score * 100;
                const facetKey = `${row['Category Mapping']}||${row['Facet Type']}`;
                if (inProductNameFacets.has(facetKey)) {
                    finalScore += 50;
                }
                row['Facet Value Score'] = Math.round(Math.min(finalScore, 100));
            });
        }

        finalReport.forEach(row => {
            row.FacetValueDetails = Object.values(row.FacetValueDetails).sort((a,b) => b['Monthly Organic Traffic'] - a['Monthly Organic Traffic']);
        });
        
        return finalReport;
    }

    function handleResultsNavigation(e) {
        const target = e.target;
        const reportContainer = target.closest('[data-report-title]');

        if (target.matches('.in-product-name-toggle')) {
            const facetKey = target.dataset.facetKey;
            if (target.checked) {
                inProductNameFacets.add(facetKey);
            } else {
                inProductNameFacets.delete(facetKey);
            }
            renderFacetPotentialAnalysisView(); // Re-render to apply new scores
            return;
        }

        const rowEditBtn = target.closest('.row-edit-btn');
        if (rowEditBtn && tableState.activeLens === 'interactive-matrix') {
            const rowId = rowEditBtn.dataset.rowId;
            renderInteractiveRowEditor(rowId);
            return;
        }

        if (target.id === 'close-row-editor') {
            clearRowEditor();
            return;
        }

        if (target.id === 'apply-selected-recommendations') {
            applySelectedSmartRecommendations();
            return;
        }

        if (target.id === 'refresh-smart-recommendations') {
            smartRecommendationSelections.clear();
            renderSmartRecommendationsView();
            showNotification('Recommendations refreshed from the latest data.', 'info');
            return;
        }

        const applyRecBtn = target.closest('.apply-recommendation-btn');
        if (applyRecBtn) {
            const recId = applyRecBtn.dataset.recId;
            if (applyRecommendationById(recId)) {
                showNotification('Recommendation applied via Manual Overrides.', 'success');
                renderSmartRecommendationsView();
            } else {
                showNotification('This recommendation was already applied.', 'info');
            }
            return;
        }

        const exportBtn = target.closest('.export-btn');
        if (exportBtn) {
            const exportType = exportBtn.dataset.exportType;
            const title = reportContainer ? reportContainer.dataset.reportTitle : 'Report';
            const fileName = title.replace(/[^\w\s]/gi, '').replace(/\s+/g, '_');
            let dataToExport = getFilteredData();
            let headersToExport = updateHeadersForTimeframe(tableState.headers, tableState.timeframe);

            // Enrich Content Gap exports with SKU IDs and counts
            if (title.includes('Content Gaps')) {
                const built = buildContentGapExport(dataToExport, headersToExport, title);
                dataToExport = built.exportData;
                headersToExport = built.exportHeaders;
            }

            if (title.includes('Category Overhaul Matrix')) {
                // Use the original data from analysisResults instead of the processed data
                const originalData = analysisResults.categoryOverhaulMatrixReport;
                const processedData = applyOverridesAndMerge(originalData, Object.keys(originalData[0] || {}), analysisResults.hasOnsiteData);
                const transformedData = transformDataForTimeframe(processedData, tableState.timeframe);
                
                // Filter out rows with 0 traffic if hideZeroTraffic is enabled
                let dataToExport = transformedData;
                if (tableState.hideZeroTraffic) {
                    const annualTrafficHeader = updateHeadersForTimeframe(['Monthly Organic Traffic'], 'annual')[0];
                    const monthlyTrafficHeader = updateHeadersForTimeframe(['Monthly Organic Traffic'], 'monthly')[0];
                    dataToExport = transformedData.filter(row => {
                        const traffic = row[annualTrafficHeader] || row[monthlyTrafficHeader];
                        return typeof traffic === 'number' && traffic > 0;
                    });
                }
                
                if (exportType === 'excel') {
                    exportCategoryOverhaulToExcel(dataToExport, headersToExport, fileName).catch(err => {
                        console.error('Error exporting to Excel:', err);
                        alert('There was an error exporting to Excel. Please try again.');
                    });
                } else if (exportType === 'json') {
                    exportCategoryOverhaulToJson(dataToExport, headersToExport, fileName);
                }
            }
            else if (title.includes('Facet Potential Analysis')) {
                // Use the original data from analysisResults instead of the processed data
                const originalData = analysisResults.categoryOverhaulMatrixReport;
                const processedData = applyOverridesAndMerge(originalData, Object.keys(originalData[0] || {}), analysisResults.hasOnsiteData);
                const regeneratedData = generateFacetPotentialFromMatrix(processedData, Object.keys(originalData[0] || {}), analysisResults.hasOnsiteData);
                const transformedData = transformDataForTimeframe(regeneratedData, tableState.timeframe);
                
                if (exportType === 'excel') {
                    exportFacetPotentialToExcel(transformedData, headersToExport, fileName);
                } else if (exportType === 'json') {
                    exportFacetPotentialToJson(transformedData, headersToExport, fileName);
                }
            } 
            else if (exportType === 'excel') {
                exportToExcel(dataToExport, headersToExport, fileName);
            } else if (exportType === 'json') {
                exportToJson(dataToExport, headersToExport, fileName, title);
            } else if (exportType === 'pdf') {
                exportToPdf(dataToExport, headersToExport, fileName, title);
            }
            return;
        }

        const lensEl = target.closest('[data-lens]');
        if (lensEl) {
            const lensType = lensEl.dataset.lens;
            if (lensType === 'keyword-gaps') renderKeywordGapAnalysisView();
            else if (lensType === 'topic-gaps') renderTopicGapAnalysisView('core');
            else if (lensType === 'keyword-threats') renderKeywordThreatsAnalysisView();
            else if (lensType === 'topic-threats') renderTopicThreatsAnalysisView('core');
            else if (lensType === 'market-share-keyword') renderKeywordMarketShareView();
            else if (lensType === 'market-share-group') renderGroupMarketShareView('core');
            else if (lensType === 'category-overhaul') renderCategoryOverhaulMatrixView();
            else if (lensType === 'facet-potential') renderFacetPotentialAnalysisView();
            else if (lensType === 'interactive-matrix') renderInteractiveCategoryMatrixView();
            else if (lensType === 'smart-recommendations') renderSmartRecommendationsView();
            else if (lensType === 'pim-sku-mapping') renderPimSkuMappingView();
            return;
        } 
        const scopeBtn = target.closest('.scope-toggle-btn');
        if (scopeBtn && scopeBtn.dataset.scope) {
            const lensType = reportContainer.dataset.reportTitle;
            if (lensType.includes('Content Gaps')) renderTopicGapAnalysisView(scopeBtn.dataset.scope);
            else if (lensType.includes('Competitive Opportunities')) renderTopicThreatsAnalysisView(scopeBtn.dataset.scope);
            else if (lensType.includes('Market Share')) renderGroupMarketShareView(scopeBtn.dataset.scope);
            return;
        }
        if (scopeBtn && scopeBtn.dataset.timeframe) {
            tableState.timeframe = scopeBtn.dataset.timeframe;
            const lensType = reportContainer.dataset.reportTitle;
            
            if (lensType.includes('Content Gaps | Individual')) renderKeywordGapAnalysisView();
            else if (lensType.includes('Content Gaps | Keyword Groups')) renderTopicGapAnalysisView(document.querySelector('.scope-toggle-btn.active[data-scope]').dataset.scope);
            else if (lensType.includes('Competitive Opportunities | Individual')) renderKeywordThreatsAnalysisView();
            else if (lensType.includes('Competitive Opportunities | Keyword Groups')) renderTopicThreatsAnalysisView(document.querySelector('.scope-toggle-btn.active[data-scope]').dataset.scope);
            else if (lensType.includes('Market Share | Individual')) renderKeywordMarketShareView();
            else if (lensType.includes('Market Share | Keyword Groups')) renderGroupMarketShareView(document.querySelector('.scope-toggle-btn.active[data-scope]').dataset.scope);
            else if (lensType.includes('Category Overhaul Matrix')) renderCategoryOverhaulMatrixView();
            else if (lensType.includes('Facet Potential Analysis')) renderFacetPotentialAnalysisView();
            return;
        }

        const viewKeywordsBtn = target.closest('.view-keywords-btn');
        if (viewKeywordsBtn) {
            const mapSource = viewKeywordsBtn.dataset.mapSource;
            const id = viewKeywordsBtn.dataset.topicId || viewKeywordsBtn.dataset.keywordGroup;
            const isNumericId = !isNaN(parseFloat(id)) && isFinite(id);
            openKeywordModal(isNumericId ? parseInt(id, 10) : id, mapSource);
            return;
        }
        
        if (target.id === 'back-to-home-btn') {
            renderInitialControlsView();
            return;
        }
        if (target.matches('.back-to-lenses-btn')) { 
            renderLensSelectionView(); 
            return; 
        }

        const headerCell = target.closest('th[data-sort-key]');
        if (headerCell) {
            const newSortKey = headerCell.dataset.sortKey;
            if (tableState.sortKey === newSortKey) tableState.sortDir = tableState.sortDir === 'asc' ? 'desc' : 'asc';
            else { tableState.sortKey = newSortKey; tableState.sortDir = 'desc'; }
            tableState.currentPage = 1;
            renderTableAndControls();
            return;
        }
        const paginationBtn = target.closest('[data-pagination-action]');
        if(paginationBtn) {
            const action = paginationBtn.dataset.paginationAction;
            if(action === 'next') tableState.currentPage++;
            if(action === 'prev') tableState.currentPage--;
            renderTableAndControls();
        }
        if(target.matches('#hide-zero-traffic-toggle')) {
            tableState.hideZeroTraffic = target.checked;
            tableState.currentPage = 1;
            renderTableAndControls();
            // Refresh Value-Based Rules dropdown if it exists and has a selected column
            const sourceColumnSelect = document.getElementById('rule-source-column');
            if (sourceColumnSelect && sourceColumnSelect.value) {
                // Trigger the change event to refresh the dropdown
                sourceColumnSelect.dispatchEvent(new Event('change'));
            }
        }
        const detailsToggle = target.closest('.keyword-details-toggle');
        if(detailsToggle) {
            const parentRow = detailsToggle.closest('tr');
            const detailsRow = parentRow.nextElementSibling;
            if (detailsRow && detailsRow.classList.contains('keyword-details-row')) {
                detailsToggle.classList.toggle('open');
                detailsRow.classList.toggle('open');
            }
        }
    }

    async function handleAnalysis() {
        // Check if we have restored project files
        const hasRestoredFiles = window.projectFileMetadata && Object.keys(window.projectFileMetadata).length > 0;
        
        // If no current project exists, create one automatically
        if (!currentProject) {
            try {
                const projectName = `Analysis ${new Date().toLocaleDateString()} ${new Date().toLocaleTimeString()}`;
                const projectData = {
                    name: projectName,
                    description: 'Auto-created project for analysis',
                    analysis_type: 'taxonomy_architecture'
                };

                const response = await fetch('/api/projects', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-API-KEY': API_KEY
                    },
                    body: JSON.stringify(projectData)
                });

                if (!response.ok) {
                    throw new Error('Failed to create project');
                }

                const newProject = await response.json();
                currentProject = newProject;
                updateProjectUI();
                showNotification(`Created project: ${projectName}`, 'success');
            } catch (error) {
                console.error('Error creating project:', error);
                showNotification('Error creating project', 'error');
                return;
            }
        }
        
        if (hasRestoredFiles) {
            // Use restored files from project
            showNotification('Using restored project files for analysis', 'info');
        } else {
            // If we have a current project, save files to it first
            if (currentProject) {
                try {
                    const fileFormData = new FormData();
                    fileFormData.append('ourFile', document.getElementById('our-file').files[0]);
                    Array.from(document.getElementById('competitor-files').files).forEach(file => { 
                        fileFormData.append('competitorFiles', file); 
                    });
                    const onsiteFile = document.getElementById('onsite-file').files[0];
                    if (onsiteFile) fileFormData.append('onsiteFile', onsiteFile);

                    const response = await fetch(`/api/projects/${currentProject.id}/files`, {
                        method: 'POST',
                        headers: { 'X-API-KEY': API_KEY },
                        body: fileFormData
                    });

                    if (!response.ok) {
                        throw new Error('Failed to save files to project');
                    }

                    showNotification('Files saved to project', 'success');
                } catch (error) {
                    console.error('Error saving files to project:', error);
                    showNotification('Warning: Could not save files to project', 'error');
                }
            }
        }

        const formData = new FormData();
        
        if (hasRestoredFiles) {
            // Use restored files - we'll need to create a special endpoint for this
            formData.append('useProjectFiles', 'true');
            formData.append('projectId', currentProject.id);
        } else {
            // Use uploaded files
        formData.append('ourFile', document.getElementById('our-file').files[0]);
        Array.from(document.getElementById('competitor-files').files).forEach(file => { formData.append('competitorFiles', file); });
        const onsiteFile = document.getElementById('onsite-file').files[0];
        if (onsiteFile) formData.append('onsiteFile', onsiteFile);
        }

        const onsiteDateRange = document.getElementById('onsite-date-range').value;
        const columnMap = {};
        document.querySelectorAll('#column-mappers select').forEach(s => { if(s.value) columnMap[s.id] = s.value; });
        const excludedKeywordsRaw = document.getElementById('branded-exclusions').value;
        const excludedKeywords = excludedKeywordsRaw.split('\n').map(kw => kw.trim()).filter(kw => kw);
        
        const lensesToRun = {
            content_gaps: document.getElementById('run_content_gaps').checked,
            competitive_opportunities: document.getElementById('run_competitive_opportunities').checked,
            market_share: document.getElementById('run_market_share').checked,
            taxonomy_analysis: document.getElementById('run_taxonomy_analysis').checked,
        };
        
        const options = { 
            columnMap, 
            excludedKeywords,
            lensesToRun,
        };

        const rankFrom = document.getElementById('rank-from').value;
        const rankTo = document.getElementById('rank-to').value;
        if (rankFrom) options.rankFrom = rankFrom;
        if (rankTo) options.rankTo = rankTo;

        if (onsiteDateRange) options.onsiteDateRange = onsiteDateRange;

        formData.append('options', JSON.stringify(options));
        try {
            ui.controlsContainer.classList.add('hidden');
            renderProgressView("Submitting task to the server...", 0);
            ui.progressContainer.classList.remove('hidden');
            document.getElementById('analyse-btn').disabled = true;
            async function startAnalysisTask(formData) {
                const protocol = window.location.protocol || 'http:';
                const hostname = window.location.hostname || '127.0.0.1';
                for (let port = 5000; port <= 5010; port++) {
                    try {
                        const apiUrl = `${protocol}//${hostname}:${port}/process`;
                        const response = await fetch(apiUrl, { method: 'POST', body: formData, headers: { 'X-API-KEY': API_KEY }, signal: AbortSignal.timeout(5000) });
                        if (response.status === 202) return { port, taskId: (await response.json()).task_id };
                        if (response.status >= 400) throw new Error((await response.json()).error || `Server on port ${port} returned an error.`);
                    } catch (error) { console.log(`Port ${port} failed...`); }
                }
                throw new Error("Could not connect to the backend server.");
            }
            const { port, taskId } = await startAnalysisTask(formData);
            if (taskId) {
                pollForResult(port, taskId);
            } else {
                throw new Error("Failed to get a valid task ID from the server.");
            }
        } catch (error) {
            ui.progressContainer.innerHTML = `<div class="p-8 bg-red-100 text-red-700 rounded-xl"><p><b>Analysis Failed:</b> ${error.message}</p></div>`;
        }
    }

    function pollForResult(port, taskId) {
        const protocol = window.location.protocol || 'http:';
        const hostname = window.location.hostname || '127.0.0.1';
        pollingInterval = setInterval(async () => {
            try {
                const apiUrl = `${protocol}//${hostname}:${port}/status/${taskId}`;
                const response = await fetch(apiUrl, { headers: { 'X-API-KEY': API_KEY } });
                const data = await response.json();
                if (data.state === 'PROGRESS') {
                    const progress = data.info;
                    const percentage = (progress.current / progress.total) * 100;
                    document.getElementById('progress-bar').style.width = `${percentage}%`;
                    document.getElementById('progress-text').textContent = progress.status;
                } else if (data.state === 'SUCCESS') {
                    clearInterval(pollingInterval);
                    analysisResults = data.result.result;
                    onAnalysisComplete();
                } else if (data.state === 'FAILURE') {
                    clearInterval(pollingInterval);
                    ui.progressContainer.innerHTML = `<div class="p-8 bg-red-100 text-red-700 rounded-xl"><p><b>Analysis Failed:</b> The analysis task failed on the server. Please check the application logs for details. Error: ${data.error}</p></div>`;
                    return;
                }
            } catch (error) {
                clearInterval(pollingInterval);
                ui.progressContainer.innerHTML = `<div class="p-8 bg-red-100 text-red-700 rounded-xl"><p><b>Polling Failed:</b> ${error.message}</p></div>`;
            }
        }, 3000); 
    }

    function onAnalysisComplete() {
        console.log('Analysis completed! Current project:', currentProject);
        ui.progressContainer.classList.add('hidden');
        ui.resultsContainer.classList.remove('hidden');
        renderLensSelectionView();
    }
    
    function renderInitialControlsView() {
        if (pollingInterval) clearInterval(pollingInterval);
        overrideRules = [];
        smartRecommendations = [];
        smartRecommendationSelections = new Set();
        inProductNameFacets = new Set(); // Reset for new analysis
        ui.resultsContainer.classList.add('hidden');
        ui.progressContainer.classList.add('hidden');
        ui.controlsContainer.classList.remove('hidden');

        const projectStatus = currentProject ? `
            <div class="mb-6 p-4 bg-green-50 border border-green-200 rounded-lg">
                <div class="flex justify-between items-center">
                    <div>
                        <h3 class="font-semibold text-green-800">Active Project: ${currentProject.name}</h3>
                        <p class="text-sm text-green-600">Your work will be saved to this project</p>
                    </div>
                    <button onclick="saveProjectState()" class="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg transition-colors">
                        💾 Save Project
                    </button>
                </div>
            </div>
        ` : '';

        // Check if we have restored file metadata
        const hasRestoredFiles = window.projectFileMetadata && Object.keys(window.projectFileMetadata).length > 0;
        const fileStatus = hasRestoredFiles ? `
            <div class="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                <div class="flex justify-between items-center">
                    <div>
                        <h4 class="font-semibold text-blue-800">📁 Files Restored from Project</h4>
                        <p class="text-sm text-blue-600">Your previously uploaded files are ready for analysis</p>
                    </div>
                    <button onclick="restoreProjectFiles()" class="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded text-sm transition-colors">
                        Restore Files
                    </button>
                </div>
            </div>
        ` : '';

        ui.controlsContainer.innerHTML = `
            <div class="bg-white p-8 rounded-xl shadow-lg max-w-4xl mx-auto">
                ${projectStatus}
                ${fileStatus}
                <div class="space-y-8">
                    <div>
                        <h2 class="text-2xl font-bold">1. Upload Your & Competitor Exports</h2>
                        <div class="grid md:grid-cols-2 gap-6 mt-4">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Your Domain's Export*</label>
                                <label class="file-input-label flex justify-center items-center w-full h-32 px-4 text-center rounded-lg" for="our-file"><span class="text-gray-500">Click to upload your CSV</span></label>
                                <input type="file" id="our-file" class="hidden" accept=".csv">
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Competitor Exports*</label>
                                <label class="file-input-label flex justify-center items-center w-full h-32 px-4 text-center rounded-lg" for="competitor-files"><span class="text-gray-500">Click to upload one or more</span></label>
                                <input type="file" id="competitor-files" class="hidden" accept=".csv" multiple>
                            </div>
                        </div>
                    </div>
                    <div class="pt-6 border-t">
                        <h2 class="text-2xl font-bold">2. On-Site Search Data (Optional)</h2>
                         <div class="mt-4">
                            <label class="block text-sm font-medium text-gray-700 mb-1">On-Site Search Data File</label>
                            <label class="file-input-label flex justify-center items-center w-full h-24 px-4 text-center rounded-lg" for="onsite-file"><span class="text-gray-500">Upload a 2-column CSV (Term, Searches)</span></label>
                            <input type="file" id="onsite-file" class="hidden" accept=".csv">
                            <label class="block text-sm font-medium text-gray-700 mb-1 mt-4">On-Site Search Date Range</label>
                            <input type="text" id="onsite-date-range" class="mt-1 block w-full p-2 border border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500" placeholder="e.g., Q1 2024">
                        </div>
                    </div>
                    <div id="column-mapping-container" class="hidden pt-6 border-t">
                        <h2 class="text-2xl font-bold">3. Map Your Columns</h2>
                        <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4" id="column-mappers"></div>
                    </div>
                    <div class="pt-6 border-t">
                         <h2 class="text-2xl font-bold">4. Filters & Exclusions</h2>
                         <div class="mt-4 space-y-4">
                            <div>
                                <label class="block text-sm font-medium text-gray-700">Rank Filter</label>
                                <p class="text-xs text-gray-500 mt-1 mb-2">Only include keywords within a specific ranking range.</p>
                                <div class="flex items-center gap-2">
                                    <input type="number" id="rank-from" class="block w-full p-2 border border-gray-300 rounded-md" placeholder="From (e.g., 1)">
                                    <span class="text-gray-500">-</span>
                                    <input type="number" id="rank-to" class="block w-full p-2 border border-gray-300 rounded-md" placeholder="To (e.g., 50)">
                                </div>
                            </div>
                            <div>
                                <div class="flex justify-between items-center">
                                    <label class="block text-sm font-medium text-gray-700">Branded Keyword Exclusions</label>
                                    <button id="load-exclusions-btn" onclick="loadDefaultExclusions()" class="text-xs font-semibold py-1 px-3 rounded border border-gray-300 hover:bg-gray-100">Load Defaults</button>
                                </div>
                                <p class="text-xs text-gray-500 mt-1 mb-2">Add any branded terms (one per line) to exclude. Any keyword containing these terms will be removed.</p>
                                <textarea id="branded-exclusions" class="mt-1 block w-full h-48 p-2 border border-gray-300 rounded-md shadow-sm"></textarea>
                            </div>
                        </div>
                    </div>
                    <div class="pt-6 border-t">
                        <h2 class="text-2xl font-bold">5. Analysis Options</h2>
                        <p class="text-sm text-gray-600 mt-2 mb-4">Select which analyses to run. Deselecting lenses can significantly speed up processing time.</p>
                        <div class="space-y-4">
                            <label class="flex items-center p-3 border rounded-lg hover:bg-gray-50">
                                <input type="checkbox" id="run_content_gaps" class="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" checked>
                                <span class="ml-3 text-sm font-medium text-gray-900">Content Gaps</span>
                            </label>
                            <label class="flex items-center p-3 border rounded-lg hover:bg-gray-50">
                                <input type="checkbox" id="run_competitive_opportunities" class="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" checked>
                                <span class="ml-3 text-sm font-medium text-gray-900">Competitive Opportunities</span>
                            </label>
                            <label class="flex items-center p-3 border rounded-lg hover:bg-gray-50">
                                <input type="checkbox" id="run_market_share" class="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" checked>
                                <span class="ml-3 text-sm font-medium text-gray-900">Market Share <span class="text-xs text-gray-500">(Requires Traffic column)</span></span>
                            </label>
                            <label class="flex items-center p-3 border rounded-lg hover:bg-gray-50">
                                <input type="checkbox" id="run_taxonomy_analysis" class="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" checked>
                                <span class="ml-3 text-sm font-medium text-gray-900">Taxonomy & Architecture <span class="text-xs text-gray-500">(Slowest)</span></span>
                            </label>
                        </div>
                    </div>
                    <div class="text-right pt-6 border-t">
                        <button id="analyse-btn" class="ts-button-primary px-8 py-3 rounded-lg shadow-md transition transform hover:scale-105 disabled:opacity-50 disabled:cursor-not-allowed" disabled>Analyse</button>
                    </div>
                </div>
            </div>`;

        setupEventListeners(); 
    }

    function renderProgressView(statusText, percentage) {
        ui.progressContainer.innerHTML = `<div class="bg-white p-8 rounded-xl shadow-lg max-w-2xl mx-auto text-center"><p class="text-xl font-bold mb-4">Analysing Your Data...</p><div class="w-full bg-gray-200 rounded-full h-4 mb-2"><div id="progress-bar" class="bg-blue-600 h-4 rounded-full progress-bar-inner" style="width: ${percentage}%"></div></div><p id="progress-text" class="text-sm text-gray-600">${statusText}</p></div>`;
    }

    function renderLensSelectionView() {
        console.log('Rendering lens selection view. Current project:', currentProject);
        
        // Ensure analysisResults exists and has the expected structure
        if (!analysisResults || typeof analysisResults !== 'object') {
            console.error('No analysis results available for rendering');
            ui.resultsContainer.innerHTML = `
                <div class="bg-white p-8 rounded-xl shadow-lg max-w-2xl mx-auto text-center">
                    <h2 class="text-2xl font-bold text-red-600 mb-4">No Analysis Results Found</h2>
                    <p class="text-gray-600 mb-4">The project doesn't contain any analysis results.</p>
                    <button onclick="renderInitialControlsView()" class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors">
                        Start New Analysis
                    </button>
                </div>
            `;
            return;
        }

        const { 
            keywordGapReport, topicGapReport, keywordThreatsReport, topicThreatsReport, 
            keywordMarketShareReport, groupMarketShareReport, categoryOverhaulMatrixReport,
            facetPotentialReport
        } = analysisResults;

        tableState.activeLens = null;
        tableState.rowEditState = null;

        // Debug logging to see what data we have
        console.log('Analysis results structure:', Object.keys(analysisResults));
        console.log('Category overhaul data:', categoryOverhaulMatrixReport);
        console.log('Facet potential data:', facetPotentialReport);

        const hasGaps = (keywordGapReport || []).length > 0 || (topicGapReport || []).length > 0;
        const hasThreats = (keywordThreatsReport || []).length > 0 || (topicThreatsReport || []).length > 0;
        const hasMarketShare = (keywordMarketShareReport || []).length > 0 || (groupMarketShareReport || []).length > 0;
        const hasOverhaulData = (categoryOverhaulMatrixReport || []).length > 0 || (facetPotentialReport || []).length > 0;
        
        // Fallback: if we have any analysis results but the specific checks failed, 
        // assume we have taxonomy data (since that's what we're focusing on)
        const hasAnyData = hasGaps || hasThreats || hasMarketShare || hasOverhaulData;
        const fallbackHasOverhaulData = !hasAnyData && Object.keys(analysisResults).length > 0;

        let html = `<div class="text-center mb-8">
            <div class="relative">
                 <h2 class="text-3xl font-bold">Analysis Complete</h2>
                 <button id="back-to-home-btn" class="absolute top-0 right-0 text-sm font-semibold text-blue-600 hover:underline">&larr; Start New Analysis</button>
            </div>
            <p class="text-lg text-gray-600 mt-2">Select a lens to explore your data.</p>
        </div><div class="space-y-8">`;
        
        if (hasGaps) {
            const hasSkuCounts = (window.contentGapSkuCounts || contentGapSkuCounts) && Object.keys(window.contentGapSkuCounts || contentGapSkuCounts || {}).length > 0;
            const skuStatusText = hasSkuCounts
                ? `SKU counts ready for ${Object.keys(window.contentGapSkuCounts || contentGapSkuCounts || {}).length} keywords.`
                : 'Upload a PIM CSV to estimate Toolstation SKU coverage for gaps.';
            
            html += `
            <div class="lens-section">
                <h3 class="text-2xl font-bold mb-4 text-gray-800 border-b pb-2">Content Gaps</h3>
                <p class="text-sm text-gray-600 mb-4">This analysis reveals keywords and topics where your competitors have ranking visibility, but your domain does not. It's designed to uncover new content opportunities and areas where you can expand your digital footprint.</p>
                
                <!-- PIM Upload Section for Content Gaps -->
                <div class="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
                    <h4 class="font-bold text-lg mb-2 text-gray-800">PIM Product Data</h4>
                    <p class="text-sm text-gray-600 mb-3">Upload your PIM product data to see estimated SKU counts for content gaps. SKU counts will be available in both Individual Keywords and Keyword Groups views.</p>
                    <div class="flex flex-wrap items-center gap-4">
                        <div class="flex-1 min-w-[200px]">
                            <label for="content-gap-pim-file-lens" class="block text-sm font-medium text-gray-700 mb-1">PIM CSV File</label>
                            <input type="file" id="content-gap-pim-file-lens" accept=".csv" class="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100">
                        </div>
                        <div class="flex-1 min-w-[200px]" id="content-gap-sku-column-selector-lens" style="display: none;">
                            <label for="content-gap-sku-id-column-lens" class="block text-sm font-medium text-gray-700 mb-1">SKU ID Column (Auto-detected)</label>
                            <select id="content-gap-sku-id-column-lens" class="block w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm">
                                <option value="">Auto-detect</option>
                            </select>
                        </div>
                        <div class="flex items-end gap-2">
                            <button id="run-content-gap-sku-btn-lens" class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-sm" disabled>
                                Estimate SKU Counts
                            </button>
                        </div>
                    </div>
                    <div id="content-gap-sku-status-lens" class="mt-2 text-sm text-gray-600">${skuStatusText}</div>
                </div>
                
                <div class="grid md:grid-cols-2 gap-6">
                    <div data-lens="keyword-gaps" class="lens-card p-6 border rounded-lg"><h3 class="font-bold text-xl">Individual Keywords</h3><p>Keywords where competitors rank but you don't.</p></div>
                    <div data-lens="topic-gaps" class="lens-card p-6 border rounded-lg"><h3 class="font-bold text-xl">Keyword Groups</h3><p>Topic groups where you have no ranking visibility.</p></div>
                </div>
            </div>`;
        }

        if (hasThreats) {
             html += `
            <div class="lens-section">
                <h3 class="text-2xl font-bold mb-4 text-gray-800 border-b pb-2">Competitive Opportunities</h3>
                <p class="text-sm text-gray-600 mb-4">This analysis pinpoints keywords and topics where competitors currently outrank you. Use these insights to identify existing pages that need optimisation to improve their search rankings and reclaim traffic.</p>
                <div class="grid md:grid-cols-2 gap-6">
                    <div data-lens="keyword-threats" class="lens-card p-6 border rounded-lg"><h3 class="font-bold text-xl">Individual Keywords</h3><p>Keywords where competitors outrank you.</p></div>
                    <div data-lens="topic-threats" class="lens-card p-6 border rounded-lg"><h3 class="font-bold text-xl">Keyword Groups</h3><p>Topic groups where competitors outrank you.</p></div>
                </div>
            </div>`;
        }

        if (hasMarketShare) {
             html += `
            <div class="lens-section">
                <h3 class="text-2xl font-bold mb-4 text-gray-800 border-b pb-2">Market Share</h3>
                <p class="text-sm text-gray-600 mb-4">This analysis estimates the organic traffic distribution between your domain and your competitors for key topics. It helps you understand your visibility and highlights areas dominated by rivals.</p>
                <div class="grid md:grid-cols-2 gap-6">
                    <div data-lens="market-share-keyword" class="lens-card p-6 border rounded-lg"><h3 class="font-bold text-xl">Individual Keywords</h3><p>Traffic share for each specific keyword.</p></div>
                    <div data-lens="market-share-group" class="lens-card p-6 border rounded-lg"><h3 class="font-bold text-xl">Keyword Groups</h3><p>Aggregated traffic share for each topic group.</p></div>
                </div>
            </div>`;
        }

        if (hasOverhaulData || fallbackHasOverhaulData) {
            html += `
            <div class="lens-section">
                <h3 class="text-2xl font-bold mb-4 text-gray-800 border-b pb-2">Taxonomy & Architecture Analysis</h3>
                <p class="text-sm text-gray-600 mb-4">This analysis automates a category overhaul by reviewing competitor URLs to extract their category, sub-type, and facet structures, then aggregates organic traffic for each combination. Use this to find high-value taxonomy gaps and inform changes to your site architecture.</p>
                
                <!-- PIM Upload Section -->
                <div class="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
                    <h4 class="font-bold text-lg mb-2 text-gray-800">PIM Product Data</h4>
                    <p class="text-sm text-gray-600 mb-3">Upload your PIM product data to see SKU counts per category-facet combination and highlight gaps in exports.</p>
                    <div class="flex flex-wrap items-center gap-4">
                        <div class="flex-1 min-w-[200px]">
                            <label for="pim-file-lens" class="block text-sm font-medium text-gray-700 mb-1">PIM CSV File</label>
                            <input type="file" id="pim-file-lens" accept=".csv" class="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100">
                        </div>
                        <div class="flex-1 min-w-[200px]" id="pim-sku-column-selector-lens" style="display: none;">
                            <label for="sku-id-column-lens" class="block text-sm font-medium text-gray-700 mb-1">SKU ID Column (Auto-detected)</label>
                            <select id="sku-id-column-lens" class="block w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm">
                                <option value="">Auto-detect</option>
                            </select>
                        </div>
                        <div class="flex items-end gap-2">
                            <button id="save-pim-btn-lens" class="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-sm" disabled>
                                Save to Project
                            </button>
                            <button id="analyze-pim-btn-lens" class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-sm" disabled>
                                Analyze PIM Data
                            </button>
                        </div>
                    </div>
                    <div id="pim-saved-status" class="mt-2 text-sm text-green-600 hidden"></div>
                    <div id="pim-analysis-status-lens" class="mt-3 hidden"></div>
                    <div id="pim-results-summary" class="mt-2 text-sm text-gray-600"></div>
                    <div id="pim-management-actions" class="mt-3">
                        <button id="clear-pim-data-btn" class="hidden bg-red-50 text-red-700 border border-red-200 px-4 py-2 rounded-lg text-sm font-semibold hover:bg-red-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
                            Delete Saved PIM Data
                        </button>
                    </div>
                </div>
                
                <div class="grid md:grid-cols-2 xl:grid-cols-4 gap-6">
                    <div data-lens="category-overhaul" class="lens-card p-6 border rounded-lg">
                        <h3 class="font-bold text-xl">Category Overhaul Matrix</h3>
                        <p>Analyse competitor category and facet structures to identify high-traffic taxonomy opportunities and inform site architecture changes.</p>
                    </div>
                    <div data-lens="facet-potential" class="lens-card p-6 border rounded-lg">
                        <h3 class="font-bold text-xl">Facet Potential Analysis</h3>
                        <p>Get a high-level view of which facet <em>types</em> (e.g., Brand, Color) drive the most traffic for each product category.</p>
                    </div>
                    <div data-lens="smart-recommendations" class="lens-card p-6 border rounded-lg">
                        <h3 class="font-bold text-xl">Smart Recommendations</h3>
                        <p>Approve AI-generated taxonomy clean-up rules to normalise labels, remove SKU noise, and instantly update the Category Overhaul Matrix.</p>
                    </div>
                    <div data-lens="interactive-matrix" class="lens-card p-6 border rounded-lg">
                        <h3 class="font-bold text-xl">Interactive Matrix Editor</h3>
                        <p>Edit individual matrix rows with conditional overrides so you can adjust values only when they appear with specific category/context combinations.</p>
                    </div>
                    <div data-lens="pim-sku-mapping" class="lens-card p-6 border rounded-lg">
                        <h3 class="font-bold text-xl">PIM SKU Mapping</h3>
                        <p>View detailed SKU mapping results showing which SKUs match each category-facet combination.</p>
                    </div>
                </div>
            </div>`;
        }

        html += `</div>`;
        ui.resultsContainer.innerHTML = html;
        
        // Setup PIM upload event listeners if Taxonomy & Architecture Analysis section exists
        if (hasOverhaulData || fallbackHasOverhaulData) {
            setupPimUploadListeners();
        }
        
        // Setup Content Gap PIM upload event listeners if Content Gaps section exists
        if (hasGaps) {
            setupContentGapPimUploadListeners();
        }
    }
    
    function setupPimUploadListeners() {
        const pimFileInput = document.getElementById('pim-file-lens');
        const analyzeBtn = document.getElementById('analyze-pim-btn-lens');
        const saveBtn = document.getElementById('save-pim-btn-lens');
        const skuColumnSelector = document.getElementById('pim-sku-column-selector-lens');
        const skuIdColumnSelect = document.getElementById('sku-id-column-lens');
        const clearPimBtn = document.getElementById('clear-pim-data-btn');
        
        if (!pimFileInput || !analyzeBtn) return;
        
        const hasSavedPimData = () => {
            const hasFile = !!(window.projectFileMetadata && window.projectFileMetadata.pim_file);
            const hasResults = !!(window.pimAnalysisResults && Object.keys(window.pimAnalysisResults).length > 0);
            return hasFile || hasResults;
        };
        
        const updateClearPimButton = () => {
            if (!clearPimBtn) return;
            if (hasSavedPimData()) {
                clearPimBtn.classList.remove('hidden');
            } else {
                clearPimBtn.classList.add('hidden');
            }
        };
        
        // Reset file input and status when view loads
        pimFileInput.value = '';
        if (skuColumnSelector) skuColumnSelector.style.display = 'none';
        analyzeBtn.disabled = true;
        if (saveBtn) saveBtn.disabled = true;
        
        const statusDiv = document.getElementById('pim-analysis-status-lens');
        const resultsSummary = document.getElementById('pim-results-summary');
        const savedStatus = document.getElementById('pim-saved-status');
        if (statusDiv) statusDiv.classList.add('hidden');
        if (resultsSummary) resultsSummary.textContent = '';
        if (savedStatus) savedStatus.classList.add('hidden');
        updateClearPimButton();
        
        // Load saved PIM file if project is loaded
        if (currentProject && window.projectFileMetadata) {
            const pimMetadata = window.projectFileMetadata.pim_file;
            if (pimMetadata && pimMetadata.original_name) {
                // Show saved file indicator
                if (savedStatus) {
                    savedStatus.textContent = `Saved: ${pimMetadata.original_name}`;
                    savedStatus.classList.remove('hidden');
                }
            }
        }
        updateClearPimButton();
        
        pimFileInput.addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (file) {
                try {
                    // Read CSV headers to detect SKU column
                    const text = await file.text();
                    const lines = text.split('\n');
                    const headers = lines[0].split(',').map(h => h.trim().replace(/^"|"$/g, ''));
                    
                    // Populate SKU column selector
                    if (skuIdColumnSelect) {
                        skuIdColumnSelect.innerHTML = '<option value="">Auto-detect</option>' + 
                            headers.map(h => `<option value="${escapeHtml(h)}">${escapeHtml(h)}</option>`).join('');
                    }
                    
                    // Show selector if hidden
                    if (skuColumnSelector) {
                        skuColumnSelector.style.display = 'block';
                    }
                    
                    // Enable analyze and save buttons
                    analyzeBtn.disabled = false;
                    if (saveBtn) saveBtn.disabled = false;
                    
                    // Clear saved status when new file is selected
                    if (savedStatus) savedStatus.classList.add('hidden');
                } catch (error) {
                    console.error('Error reading file:', error);
                    showNotification('Error reading file. Please ensure it is a valid CSV file.', 'error');
                }
            }
        });
        
        if (clearPimBtn) {
            clearPimBtn.addEventListener('click', async () => {
                if (!currentProject) {
                    showNotification('Please select or create a project first.', 'error');
                    return;
                }
                
                if (!confirm('Delete the saved PIM data for this project? This cannot be undone.')) {
                    return;
                }
                
                const originalText = clearPimBtn.textContent;
                clearPimBtn.disabled = true;
                clearPimBtn.textContent = 'Deleting...';
                
                try {
                    const protocol = window.location.protocol || 'http:';
                    const hostname = window.location.hostname || '127.0.0.1';
                    const apiUrl = `${protocol}//${hostname}:5000/api/projects/${currentProject.id}/pim_data`;
                    
                    const response = await fetch(apiUrl, {
                        method: 'DELETE',
                        headers: {
                            'X-API-KEY': API_KEY
                        }
                    });
                    
                    if (!response.ok) {
                        let message = 'Failed to delete saved PIM data';
                        try {
                            const errorData = await response.json();
                            message = errorData.error || message;
                        } catch (err) {
                            // Ignore JSON parse errors
                        }
                        throw new Error(message);
                    }
                    
                    if (window.projectFileMetadata && window.projectFileMetadata.pim_file) {
                        delete window.projectFileMetadata.pim_file;
                    }
                    window.pimAnalysisResults = null;
                    
                    pimFileInput.value = '';
                    if (skuColumnSelector) skuColumnSelector.style.display = 'none';
                    analyzeBtn.disabled = true;
                    if (saveBtn) saveBtn.disabled = true;
                    if (statusDiv) statusDiv.classList.add('hidden');
                    if (resultsSummary) {
                        resultsSummary.textContent = '';
                        resultsSummary.className = 'mt-2 text-sm text-gray-600';
                    }
                    if (savedStatus) savedStatus.classList.add('hidden');
                    
                    showNotification('Saved PIM data removed from this project.', 'success');
                } catch (error) {
                    console.error('Error deleting PIM data:', error);
                    showNotification(error.message || 'Error deleting PIM data', 'error');
                } finally {
                    clearPimBtn.disabled = false;
                    clearPimBtn.textContent = originalText;
                    updateClearPimButton();
                }
            });
        }
        
        // Save PIM file to project
        if (saveBtn) {
            saveBtn.addEventListener('click', async () => {
                if (!currentProject) {
                    showNotification('Please select or create a project first.', 'error');
                    return;
                }
                
                const fileInput = document.getElementById('pim-file-lens');
                if (!fileInput || !fileInput.files || !fileInput.files[0]) {
                    showNotification('Please select a PIM CSV file first.', 'error');
                    return;
                }
                
                const file = fileInput.files[0];
                saveBtn.disabled = true;
                saveBtn.textContent = 'Saving...';
                
                try {
                    const formData = new FormData();
                    formData.append('pimFile', file);
                    
                    const protocol = window.location.protocol || 'http:';
                    const hostname = window.location.hostname || '127.0.0.1';
                    const apiUrl = `${protocol}//${hostname}:5000/api/projects/${currentProject.id}/files`;
                    
                    const response = await fetch(apiUrl, {
                        method: 'POST',
                        headers: {
                            'X-API-KEY': API_KEY
                        },
                        body: formData
                    });
                    
                    if (!response.ok) {
                        const errorData = await response.json();
                        throw new Error(errorData.error || 'Failed to save PIM file');
                    }
                    
                    const result = await response.json();
                    
                    // Update saved status
                    if (savedStatus) {
                        savedStatus.textContent = `Saved: ${file.name}`;
                        savedStatus.classList.remove('hidden');
                    }
                    
                    // Update project file metadata
                    if (!window.projectFileMetadata) {
                        window.projectFileMetadata = {};
                    }
                    window.projectFileMetadata.pim_file = {
                        path: result.saved_files.pim_file,
                        original_name: file.name
                    };
                    
                    updateClearPimButton();
                    showNotification('PIM file saved to project successfully!', 'success');
                } catch (error) {
                    console.error('Error saving PIM file:', error);
                    showNotification(`Error saving PIM file: ${error.message}`, 'error');
                } finally {
                    saveBtn.disabled = false;
                    saveBtn.textContent = 'Save to Project';
                }
            });
        }
        
        analyzeBtn.addEventListener('click', async () => {
            const fileInput = document.getElementById('pim-file-lens');
            if (!fileInput || !fileInput.files || !fileInput.files[0]) {
                showNotification('Please select a PIM CSV file first.', 'error');
                return;
            }
            
            const file = fileInput.files[0];
            const skuColumn = skuIdColumnSelect ? skuIdColumnSelect.value : null;
            
            // Get category-facet map from Category Overhaul Matrix
            // Use the processed data (with overrides applied) if available, otherwise use raw data
            const { categoryOverhaulMatrixReport, hasOnsiteData } = analysisResults;
            if (!categoryOverhaulMatrixReport || categoryOverhaulMatrixReport.length === 0) {
                showNotification('Category Overhaul Matrix data is required. Please run an analysis first.', 'error');
                return;
            }
            
            // Process the data the same way the Category Overhaul Matrix view does
            // This applies user overrides and merges rows
            const baseHeaders = Object.keys(categoryOverhaulMatrixReport[0] || {});
            const excludeFromAggregation = [];
            if (tableState.hideFeatures) {
                excludeFromAggregation.push('Features', 'Discovered Features');
            }
            
            // Apply overrides and merge (same as renderCategoryOverhaulMatrixView)
            const modifiedData = applyOverridesAndMerge(categoryOverhaulMatrixReport, baseHeaders, hasOnsiteData, excludeFromAggregation);
            const transformedData = transformDataForTimeframe(modifiedData, tableState.timeframe);
            
            // Use the processed data for building category-facet pairs
            const categoryFacetMap = buildCategoryFacetPairs(
                transformedData, 
                Object.keys(transformedData[0] || {})
            );
            
            analyzeBtn.disabled = true;
            analyzeBtn.textContent = 'Analyzing...';
            
            if (statusDiv) {
                statusDiv.className = 'p-3 bg-blue-50 border border-blue-200 rounded-lg text-blue-700 text-sm';
                statusDiv.textContent = 'Analyzing PIM data... This may take a moment.';
                statusDiv.classList.remove('hidden');
            }
            
            try {
                // Prepare form data
                const formData = new FormData();
                formData.append('pimFile', file);
                formData.append('categoryFacetMap', JSON.stringify(categoryFacetMap));
                if (skuColumn) {
                    formData.append('skuIdColumn', skuColumn);
                }
                
                    // Call API - use full URL with port
                    let response;
                    let result;
                    let apiError = null;
                    
                    // Try different ports (5000-5010) like the main analysis does
                    const protocol = window.location.protocol || 'http:';
                    const hostname = window.location.hostname || '127.0.0.1';
                    for (let port = 5000; port <= 5010; port++) {
                        try {
                            const apiUrl = `${protocol}//${hostname}:${port}/api/pim/analyze`;
                            response = await fetch(apiUrl, {
                            method: 'POST',
                            headers: {
                                'X-API-KEY': API_KEY
                            },
                            body: formData,
                            signal: AbortSignal.timeout(360000) // 6 minute timeout (360 seconds) - backend allows up to 5 minutes
                        });
                        
                        // Check if response is JSON by checking content-type header
                        const contentType = response.headers.get('content-type') || '';
                        
                        if (response.status === 202 && contentType.includes('application/json')) {
                            // Async task started - get task_id and poll for results
                            const taskData = await response.json();
                            if (taskData.task_id) {
                                // Start polling for results
                                await pollPimTaskResult(hostname, port, taskData.task_id, statusDiv, resultsSummary);
                                return; // Exit early, polling will handle completion
                            } else {
                                throw new Error('Task ID not received from server');
                            }
                        } else if (response.ok && contentType.includes('application/json')) {
                            // Immediate success - parse as JSON (backward compatibility)
                            result = await response.json();
                            break; // Success, exit loop
                        } else {
                            // Error response - try to parse as JSON, fallback to text
                            let errorMessage = `Server error on port ${port} (Status: ${response.status})`;
                            try {
                                if (contentType.includes('application/json')) {
                                    const errorData = await response.json();
                                    errorMessage = errorData.error || errorMessage;
                                } else {
                                    // Not JSON, read as text
                                    const text = await response.text();
                                    console.error(`Port ${port} returned non-JSON:`, text.substring(0, 500));
                                    if (text.trim().startsWith('<!')) {
                                        errorMessage = `Server on port ${port} returned HTML error page. Check if the endpoint exists.`;
                                    } else {
                                        errorMessage = `Server error: ${text.substring(0, 200)}`;
                                    }
                                }
                            } catch (parseError) {
                                // Couldn't parse response
                                console.error(`Failed to parse error response from port ${port}:`, parseError);
                            }
                            apiError = new Error(errorMessage);
                            continue; // Try next port
                        }
                        } catch (error) {
                            if (error.name === 'AbortError') {
                                apiError = new Error(`Request to port ${port} timed out`);
                            } else {
                                apiError = error;
                            }
                            console.log(`Port ${port} failed: ${error.message}`);
                            continue; // Try next port
                        }
                    }
                    
                    if (!result) {
                        throw apiError || new Error('Could not connect to backend server on any port (5000-5010)');
                    }
                
                // Store PIM results globally for use in exports
                window.pimAnalysisResults = result;
                updateClearPimButton();
                
                // Update status
                if (statusDiv) {
                    statusDiv.className = 'p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm';
                    statusDiv.innerHTML = `
                        <div class="font-semibold">Analysis Complete!</div>
                        <div class="mt-1">Total SKUs: ${result.total_skus} | Matched SKUs: ${result.matched_skus} (${Math.round(result.matched_skus / result.total_skus * 100)}%)</div>
                    `;
                }
                
                // Show results summary
                if (resultsSummary) {
                    resultsSummary.textContent = `✓ PIM data loaded. Exports will now highlight rows/values without SKUs.`;
                    resultsSummary.className = 'mt-2 text-sm text-green-600';
                }
                
                showNotification('PIM analysis complete! Exports will now show SKU availability.', 'success');
                
            } catch (error) {
                console.error('Error analyzing PIM file:', error);
                showNotification(`Error analyzing PIM file: ${error.message}`, 'error');
                
                if (statusDiv) {
                    statusDiv.className = 'p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm';
                    statusDiv.textContent = `Error: ${error.message}`;
                }
            } finally {
                // Only re-enable if not polling (polling will handle completion)
                if (!window.pimPollingInterval) {
                    analyzeBtn.disabled = false;
                    analyzeBtn.textContent = 'Analyze PIM Data';
                }
            }
        });
        
        // Polling function for async PIM analysis task
        async function pollPimTaskResult(hostname, port, taskId, statusDiv, resultsSummary) {
            const protocol = window.location.protocol || 'http:';
            const analyzeBtn = document.getElementById('analyze-pim-btn-lens');
            
            window.pimPollingInterval = setInterval(async () => {
                try {
                    const apiUrl = `${protocol}//${hostname}:${port}/api/pim/status/${taskId}`;
                    const response = await fetch(apiUrl, { headers: { 'X-API-KEY': API_KEY } });
                    const data = await response.json();
                    
                    if (data.state === 'PROGRESS') {
                        // Update progress display
                        const progress = data.info;
                        const percentage = progress.total > 0 ? (progress.current / progress.total) * 100 : 0;
                        
                        if (statusDiv) {
                            statusDiv.className = 'p-3 bg-blue-50 border border-blue-200 rounded-lg text-blue-700 text-sm';
                            statusDiv.innerHTML = `
                                <div class="font-semibold">${progress.status || 'Processing...'}</div>
                                <div class="mt-2">
                                    <div class="w-full bg-gray-200 rounded-full h-2">
                                        <div class="bg-blue-600 h-2 rounded-full transition-all" style="width: ${percentage}%"></div>
                                    </div>
                                    <div class="mt-1 text-xs">${progress.current || 0} / ${progress.total || 0}</div>
                                </div>
                            `;
                        }
                    } else if (data.state === 'SUCCESS') {
                        // Task completed successfully
                        clearInterval(window.pimPollingInterval);
                        window.pimPollingInterval = null;
                        
                        // Handle different result structures
                        // Task returns: {'status': 'SUCCESS', 'result': {...}}
                        // Status endpoint returns: {'state': 'SUCCESS', 'result': {'status': 'SUCCESS', 'result': {...}}}
                        let result = null;
                        if (data.result && data.result.result) {
                            // Nested structure: {state: 'SUCCESS', result: {status: 'SUCCESS', result: {...}}}
                            result = data.result.result;
                        } else if (data.result && data.result.status === 'SUCCESS' && data.result.result) {
                            // Same nested structure
                            result = data.result.result;
                        } else if (data.result) {
                            // Direct result structure (fallback)
                            result = data.result;
                        } else {
                            console.error('Unexpected result structure:', data);
                            throw new Error('Unexpected result structure from server');
                        }
                        
                        // Validate result structure
                        if (!result || typeof result !== 'object') {
                            console.error('Invalid result:', result);
                            throw new Error('Invalid result structure received from server');
                        }
                        
                        // Store PIM results globally
                        window.pimAnalysisResults = result;
                        updateClearPimButton();
                        
                        // Update status
                        if (statusDiv) {
                            const totalSkus = result.total_skus || 0;
                            const matchedSkus = result.matched_skus || 0;
                            const percentage = totalSkus > 0 ? Math.round(matchedSkus / totalSkus * 100) : 0;
                            
                            statusDiv.className = 'p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm';
                            statusDiv.innerHTML = `
                                <div class="font-semibold">Analysis Complete!</div>
                                <div class="mt-1">Total SKUs: ${totalSkus} | Matched SKUs: ${matchedSkus} (${percentage}%)</div>
                            `;
                        }
                        
                        // Show results summary
                        if (resultsSummary) {
                            resultsSummary.textContent = `✓ PIM data loaded. Exports will now highlight rows/values without SKUs.`;
                            resultsSummary.className = 'mt-2 text-sm text-green-600';
                            resultsSummary.classList.remove('hidden');
                        }
                        
                        // Re-enable button
                        if (analyzeBtn) {
                            analyzeBtn.disabled = false;
                            analyzeBtn.textContent = 'Analyze PIM Data';
                        }
                        
                        // Display results
                        displayPimAnalysisResults(result);
                        
                        showNotification('PIM analysis complete! Exports will now show SKU availability.', 'success');
                    } else if (data.state === 'FAILURE') {
                        // Task failed
                        clearInterval(window.pimPollingInterval);
                        window.pimPollingInterval = null;
                        
                        const errorMsg = data.error || 'Unknown error occurred';
                        
                        if (statusDiv) {
                            statusDiv.className = 'p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm';
                            statusDiv.textContent = `Error: ${errorMsg}`;
                        }
                        
                        // Re-enable button
                        if (analyzeBtn) {
                            analyzeBtn.disabled = false;
                            analyzeBtn.textContent = 'Analyze PIM Data';
                        }
                        
                        showNotification(`PIM analysis failed: ${errorMsg}`, 'error');
                    }
                } catch (error) {
                    clearInterval(window.pimPollingInterval);
                    window.pimPollingInterval = null;
                    
                    console.error('Error polling PIM task status:', error);
                    
                    if (statusDiv) {
                        statusDiv.className = 'p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm';
                        statusDiv.textContent = `Error polling task status: ${error.message}`;
                    }
                    
                    // Re-enable button
                    if (analyzeBtn) {
                        analyzeBtn.disabled = false;
                        analyzeBtn.textContent = 'Analyze PIM Data';
                    }
                }
            }, 2000); // Poll every 2 seconds
        }
    }
    
    const monthlyToAnnualCols = [
        'Monthly Google Searches', 'Total Monthly Google Searches', 'Monthly Organic Traffic',
        'Top Competitor Monthly Organic Traffic', 'Total Competitor Monthly Organic Traffic',
        'Our Monthly Organic Traffic', 'Best Competitor Monthly Organic Traffic',
        'Monthly Traffic Growth Opportunity', 'Total Our Monthly Traffic', 'Total Best Competitor Monthly Traffic',
        'Total Monthly Traffic Growth Opportunity', 'Total Monthly Google Traffic'
    ];
    
    function updateHeadersForTimeframe(headers, timeframe) {
        if (timeframe === 'annual') {
            return headers.map(h => h.replace(/Monthly/g, 'Annual'));
        }
        return headers.map(h => h.replace(/Annual/g, 'Monthly'));
    }

    function transformDataForTimeframe(data, timeframe) {
        if (timeframe === 'monthly') return JSON.parse(JSON.stringify(data));

        const dataToAnnualize = JSON.parse(JSON.stringify(data));

        const processObject = (obj) => {
            if (Array.isArray(obj)) {
                return obj.map(processObject);
            }
            if (obj !== null && typeof obj === 'object') {
                const newObj = {};
                for (const key of Object.keys(obj)) {
                    let value = obj[key];
                    const newKey = key.replace(/Monthly/g, 'Annual');

                    // Annualize metrics
                    if (monthlyToAnnualCols.includes(key) && typeof value === 'number') {
                        value *= 12;
                    } else if (Array.isArray(value) && value.length === 2 && typeof value[1] === 'number') {
                        // Handle market share format [percentage, traffic]
                        value = [value[0], value[1] * 12];
                    }
                    
                    newObj[newKey] = processObject(value);
                }
                return newObj;
            }
            return obj;
        };

        return dataToAnnualize.map(processObject);
    }

    function escapeHtml(value) {
        if (value === null || value === undefined) return '';
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function normalizeValueForGrouping(value) {
        if (value === null || value === undefined) return '';
        return String(value)
            .toLowerCase()
            .replace(/&/g, ' and ')
            .replace(/\+/g, ' ')
            .replace(/[^a-z0-9]+/g, ' ')
            .replace(/\s+/g, ' ')
            .trim();
    }

    function isFeatureColumn(columnName) {
        if (!columnName) return false;
        const normalized = columnName.toLowerCase();
        return normalized === 'features' || normalized === 'discovered features';
    }

    function getFacetHeaders(headers = []) {
        if (!Array.isArray(headers)) return [];
        return headers.filter(h => 
            h &&
            h !== 'Category Mapping' &&
            h !== 'KeywordDetails' &&
            h !== 'FacetValueDetails' &&
            !h.includes('Traffic') &&
            !h.includes('Searches') &&
            !isFeatureColumn(h)
        );
    }

    function normalizeConditions(conditions = {}) {
        const entries = Object.entries(conditions || {}).map(([col, val]) => [col, val === undefined || val === null ? '' : String(val).trim()]);
        entries.sort((a, b) => a[0].localeCompare(b[0]));
        return JSON.stringify(entries);
    }

    function matchesRuleConditions(rule, rowFacets = {}) {
        if (!rule || !rule.conditions || Object.keys(rule.conditions).length === 0) return true;
        return Object.entries(rule.conditions).every(([column, expectedValue]) => {
            const required = expectedValue === undefined || expectedValue === null ? '' : String(expectedValue).trim();
            const cellValue = rowFacets[column];
            if (cellValue === null || cellValue === undefined || String(cellValue).trim() === '') {
                return required === '';
            }
            const cellValues = String(cellValue).split('|').map(v => v.trim()).filter(Boolean);
            return required === '' ? cellValues.length === 0 : cellValues.includes(required);
        });
    }

    function hasMatchingOverride({ action, sourceColumn, value, newValue = null, targetColumn = null, moveMode = null, conditions = null }) {
        const trimmedValue = value === null || value === undefined ? '' : String(value).trim();
        const conditionsKey = normalizeConditions(conditions || {});
        return overrideRules.some(rule => {
            if (rule.action !== action) return false;
            if (rule.sourceColumn !== sourceColumn) return false;
            const ruleValue = rule.value === null || rule.value === undefined ? '' : String(rule.value).trim();
            if (ruleValue !== trimmedValue) return false;
            const ruleConditionsKey = normalizeConditions(rule.conditions || {});
            if (ruleConditionsKey !== conditionsKey) return false;
            if (action === 'change') {
                return (rule.newValue || '').trim() === (newValue || '').trim();
            }
            if (action === 'move') {
                return rule.targetColumn === targetColumn && rule.moveMode === moveMode;
            }
            return true;
        });
    }

    function buildSmartRecommendations(matrixData = [], headers = []) {
        if (!Array.isArray(matrixData) || matrixData.length === 0) return [];
        const facetHeaders = getFacetHeaders(headers);
        if (facetHeaders.length === 0) return [];

        const normalizedGroups = new Map();
        const columnValueStats = {};
        const crossColumnValueMap = new Map();

        matrixData.forEach((row, rowIndex) => {
            facetHeaders.forEach(column => {
                const rawValue = row[column];
                if (rawValue === null || rawValue === undefined) return;
                const values = String(rawValue).split('|').map(v => v.trim()).filter(Boolean);
                values.forEach(value => {
                    const normalized = normalizeValueForGrouping(value);
                    if (!normalized) return;
                    const groupKey = `${column}||${normalized}`;
                    let groupEntry = normalizedGroups.get(groupKey);
                    if (!groupEntry) {
                        groupEntry = { column, normalized, rows: new Set(), values: new Map() };
                        normalizedGroups.set(groupKey, groupEntry);
                    }
                    groupEntry.rows.add(rowIndex);
                    let valueEntry = groupEntry.values.get(value);
                    if (!valueEntry) {
                        valueEntry = { count: 0, rows: new Set() };
                        groupEntry.values.set(value, valueEntry);
                    }
                    valueEntry.count += 1;
                    valueEntry.rows.add(rowIndex);

                    if (!crossColumnValueMap.has(normalized)) {
                        crossColumnValueMap.set(normalized, new Map());
                    }
                    const columnMap = crossColumnValueMap.get(normalized);
                    let columnEntry = columnMap.get(column);
                    if (!columnEntry) {
                        columnEntry = { count: 0, rows: new Set(), rawValues: new Map() };
                        columnMap.set(column, columnEntry);
                    }
                    columnEntry.count += 1;
                    columnEntry.rows.add(rowIndex);
                    columnEntry.rawValues.set(value, (columnEntry.rawValues.get(value) || 0) + 1);

                    if (column === 'Category Mapping') {
                        if (!columnValueStats[value]) {
                            columnValueStats[value] = { count: 0, rows: new Set() };
                        }
                        columnValueStats[value].count += 1;
                        columnValueStats[value].rows.add(rowIndex);
                    }
                });
            });
        });

        const MAX_RECOMMENDATIONS = 200;
        const recommendations = [];
        const addedIds = new Set();

        const createRecommendationId = (...parts) => parts.join('-').replace(/[^a-zA-Z0-9-]+/g, '_');

        normalizedGroups.forEach(groupEntry => {
            if (recommendations.length >= MAX_RECOMMENDATIONS) return;
            if (!groupEntry || groupEntry.values.size < 2) return;
            const sortedValues = [...groupEntry.values.entries()].sort((a, b) => b[1].count - a[1].count);
            const canonicalValue = sortedValues[0][0];

            sortedValues.slice(1).forEach(([value, meta]) => {
                if (recommendations.length >= MAX_RECOMMENDATIONS) return;
                if (value === canonicalValue) return;

                if (hasMatchingOverride({ action: 'change', sourceColumn: groupEntry.column, value, newValue: canonicalValue })) {
                    return;
                }

                const recommendationId = createRecommendationId('normalize', groupEntry.column, normalizeValueForGrouping(value), normalizeValueForGrouping(canonicalValue));
                if (addedIds.has(recommendationId)) return;

                const affectedRows = meta.rows ? meta.rows.size : meta.count;
                const totalRows = groupEntry.rows ? groupEntry.rows.size : affectedRows;
                const confidence = Math.min(95, Math.round((affectedRows / Math.max(totalRows, 1)) * 100));

                recommendations.push({
                    id: recommendationId,
                    action: 'change',
                    sourceColumn: groupEntry.column,
                    value,
                    newValue: canonicalValue,
                    affectedRows,
                    confidence,
                    recommendationType: 'normalise',
                    reason: `Standardise "${value}" to match the most common value "${canonicalValue}" seen in ${totalRows} rows.`,
                });
                addedIds.add(recommendationId);
            });
        });

        Object.entries(columnValueStats).forEach(([value, stats]) => {
            if (recommendations.length >= MAX_RECOMMENDATIONS) return;
            if (!value || !stats) return;
            const trimmedValue = value.trim();
            if (!trimmedValue) return;

            const appearsProductLike = trimmedValue.length > 40 || /[0-9]/.test(trimmedValue);
            if (stats.count <= 2 && appearsProductLike) {
                if (hasMatchingOverride({ action: 'remove', sourceColumn: 'Category Mapping', value: trimmedValue })) {
                    return;
                }
                const recommendationId = createRecommendationId('remove', 'CategoryMapping', normalizeValueForGrouping(trimmedValue));
                if (addedIds.has(recommendationId)) return;

                recommendations.push({
                    id: recommendationId,
                    action: 'remove',
                    sourceColumn: 'Category Mapping',
                    value: trimmedValue,
                    affectedRows: stats.rows ? stats.rows.size : stats.count,
                    confidence: 65,
                    recommendationType: 'cleanup',
                    reason: `This value only appears ${stats.count} time(s) and looks like a specific product/SKU. Removing it keeps the taxonomy focused on categories.`,
                });
                addedIds.add(recommendationId);
            }
        });

        recommendations.sort((a, b) => b.affectedRows - a.affectedRows);

        crossColumnValueMap.forEach((columnMap, normalized) => {
            if (recommendations.length >= MAX_RECOMMENDATIONS) return;
            if (!columnMap || columnMap.size < 2) return;

            const sortedColumns = [...columnMap.entries()].sort((a, b) => b[1].count - a[1].count);
            const [dominantColumn, dominantData] = sortedColumns[0];
            if (!dominantData || dominantData.count < 4) return;

            sortedColumns.slice(1).forEach(([sourceColumn, sourceData]) => {
                if (recommendations.length >= MAX_RECOMMENDATIONS) return;
                if (!sourceData || sourceColumn === dominantColumn) return;
                if (sourceData.count < 2) return;

                const dominanceRatio = dominantData.count / sourceData.count;
                if (dominanceRatio < 1.5 && dominantData.count - sourceData.count < 5) return;

                const sourceTopValue = [...sourceData.rawValues.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
                const targetTopValue = [...dominantData.rawValues.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
                if (!sourceTopValue) return;

                if (hasMatchingOverride({
                    action: 'move',
                    sourceColumn,
                    value: sourceTopValue,
                    targetColumn: dominantColumn,
                    moveMode: 'replace'
                })) {
                    return;
                }

                const recommendationId = createRecommendationId('move', sourceColumn, normalizeValueForGrouping(sourceTopValue), dominantColumn);
                if (addedIds.has(recommendationId)) return;

                const affectedRows = sourceData.rows ? sourceData.rows.size : sourceData.count;
                const confidence = Math.min(92, Math.round((dominantData.count / (dominantData.count + sourceData.count)) * 100));

                recommendations.push({
                    id: recommendationId,
                    action: 'move',
                    sourceColumn,
                    targetColumn: dominantColumn,
                    value: sourceTopValue,
                    moveMode: 'replace',
                    targetValueHint: targetTopValue,
                    affectedRows,
                    confidence,
                    recommendationType: 'relocate',
                    reason: `Appears ${dominantData.count}× in "${dominantColumn}" but only ${sourceData.count}× in "${sourceColumn}". Move it to keep similar values together.`,
                });
                addedIds.add(recommendationId);
            });
        });

        return recommendations.slice(0, MAX_RECOMMENDATIONS);
    }

    function updateSmartRecommendationSelectionCount() {
        const selectionCountEl = document.getElementById('selected-recommendations-count');
        if (selectionCountEl) {
            selectionCountEl.textContent = `${smartRecommendationSelections.size} selected`;
        }
        const applyBtn = document.getElementById('apply-selected-recommendations');
        if (applyBtn) {
            applyBtn.disabled = smartRecommendationSelections.size === 0;
        }
    }

    function applyRecommendationById(recId) {
        if (!recId) return false;
        const recommendation = smartRecommendations.find(rec => rec.id === recId);
        if (!recommendation) return false;
        const wasApplied = addOverrideRuleFromRecommendation(recommendation);
        if (wasApplied) {
            smartRecommendationSelections.delete(recId);
        }
        return wasApplied;
    }

    function applySelectedSmartRecommendations() {
        if (smartRecommendationSelections.size === 0) {
            alert('Select at least one recommendation to apply.');
            return;
        }
        let appliedCount = 0;
        [...smartRecommendationSelections].forEach(recId => {
            if (applyRecommendationById(recId)) {
                appliedCount += 1;
            }
        });
        if (appliedCount > 0) {
            showNotification(`Applied ${appliedCount} recommendation${appliedCount === 1 ? '' : 's'}.`, 'success');
        } else {
            showNotification('No new rules were added. They may already exist.', 'info');
        }
        renderSmartRecommendationsView();
    }

    function addOverrideRuleFromRecommendation(recommendation) {
        if (!recommendation) return false;
        let newRule = null;
        if (recommendation.action === 'change') {
            if (hasMatchingOverride({ action: 'change', sourceColumn: recommendation.sourceColumn, value: recommendation.value, newValue: recommendation.newValue })) {
                return false;
            }
            newRule = {
                action: 'change',
                sourceColumn: recommendation.sourceColumn,
                value: recommendation.value,
                newValue: recommendation.newValue
            };
        } else if (recommendation.action === 'remove') {
            if (hasMatchingOverride({ action: 'remove', sourceColumn: recommendation.sourceColumn, value: recommendation.value })) {
                return false;
            }
            newRule = {
                action: 'remove',
                sourceColumn: recommendation.sourceColumn,
                value: recommendation.value
            };
        } else if (recommendation.action === 'move') {
            if (hasMatchingOverride({
                action: 'move',
                sourceColumn: recommendation.sourceColumn,
                value: recommendation.value,
                targetColumn: recommendation.targetColumn,
                moveMode: recommendation.moveMode || 'replace'
            })) {
                return false;
            }
            newRule = {
                action: 'move',
                sourceColumn: recommendation.sourceColumn,
                targetColumn: recommendation.targetColumn,
                value: recommendation.value,
                moveMode: recommendation.moveMode || 'replace',
                isNew: false
            };
        }

        if (!newRule) return false;

        overrideRules.push({ id: Date.now() + Math.random(), ...newRule });
        return true;
    }

    function getContentGapSkuTerms() {
        const terms = new Set();
        if (analysisResults.keywordGapReport && Array.isArray(analysisResults.keywordGapReport)) {
            analysisResults.keywordGapReport.forEach(row => {
                const term = row && row.Keyword ? String(row.Keyword).trim() : '';
                if (term) terms.add(term);
            });
        }
        return Array.from(terms);
    }

    function renderContentGapSkuControls() {
        const hasCounts = contentGapSkuCounts && Object.keys(contentGapSkuCounts).length > 0;
        const statusText = hasCounts
            ? 'SKU counts loaded'
            : 'Upload a PIM CSV to estimate Toolstation SKU coverage for gaps.';

        return `
            <div id="content-gap-sku-controls" class="flex flex-wrap items-center gap-2">
                <label class="text-xs font-semibold text-gray-700">PIM CSV</label>
                <input type="file" id="content-gap-pim-file" accept=".csv" class="text-xs text-gray-600 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100">
                <div id="content-gap-sku-column-wrapper" class="hidden">
                    <select id="content-gap-sku-id-column" class="text-xs px-2 py-1 border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-blue-500">
                        <option value="">Auto-detect SKU column</option>
                    </select>
                </div>
                <button id="run-content-gap-sku-btn" class="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded-md text-xs font-semibold disabled:opacity-50 disabled:cursor-not-allowed" disabled>
                    Estimate SKU Counts
                </button>
                <div id="content-gap-sku-status" class="text-xs text-gray-600">${statusText}</div>
            </div>
        `;
    }

    function handleContentGapSkuResult(result, statusDiv, actionBtn) {
        let payload = result;
        if (payload && payload.result) {
            payload = payload.result;
        }
        if (payload && payload.status === 'SUCCESS' && payload.result) {
            payload = payload.result;
        }

        const counts = (payload && (payload.sku_counts || payload.skuCounts)) || null;
        if (counts && typeof counts === 'object') {
            contentGapSkuCounts = counts;
            window.contentGapSkuCounts = counts;
            const countMessage = `SKU counts ready for ${Object.keys(counts).length} keywords.`;
            
            // Update status in both the lens-level view and current view (if applicable)
            if (statusDiv) {
                statusDiv.textContent = countMessage;
                statusDiv.className = statusDiv.id === 'content-gap-sku-status-lens' 
                    ? 'mt-2 text-sm text-green-600' 
                    : 'text-xs text-green-700';
            }
            
            // Also update lens-level status if we're in a detail view
            const lensStatusDiv = document.getElementById('content-gap-sku-status-lens');
            if (lensStatusDiv && lensStatusDiv !== statusDiv) {
                lensStatusDiv.textContent = countMessage;
                lensStatusDiv.className = 'mt-2 text-sm text-green-600';
            }
            
            showNotification('Estimated SKU counts calculated. Available in all Content Gap views.', 'success');
            
            // If we're in a detail view, refresh it; otherwise the counts will be available when switching views
            const container = document.querySelector('[data-report-title]');
            if (container) {
                const title = container.dataset.reportTitle || '';
                if (title.includes('Content Gaps')) {
                    rerenderCurrentContentGapLens();
                }
            }
        } else if (statusDiv) {
            statusDiv.textContent = 'Received response, but no SKU counts were found.';
            statusDiv.className = statusDiv.id === 'content-gap-sku-status-lens' 
                ? 'mt-2 text-sm text-yellow-600' 
                : 'text-xs text-yellow-700';
        }

        if (actionBtn) {
            actionBtn.disabled = false;
            actionBtn.textContent = 'Estimate SKU Counts';
        }
    }

    async function startContentGapSkuPolling(hostname, port, taskId, statusDiv, actionBtn) {
        const protocol = window.location.protocol || 'http:';
        if (window.contentGapSkuPollingInterval) {
            clearInterval(window.contentGapSkuPollingInterval);
        }

        window.contentGapSkuPollingInterval = setInterval(async () => {
            try {
                const apiUrl = `${protocol}//${hostname}:${port}/api/pim/sku_counts/status/${taskId}`;
                const response = await fetch(apiUrl, { headers: { 'X-API-KEY': API_KEY } });
                const data = await response.json();

                if (data.state === 'PROGRESS' && statusDiv) {
                    const progress = data.info || {};
                    const percentage = progress.total > 0 ? Math.round((progress.current / progress.total) * 100) : 0;
                    statusDiv.textContent = `${progress.status || 'Processing'} (${percentage}%)`;
                    statusDiv.className = statusDiv.id === 'content-gap-sku-status-lens' 
                        ? 'mt-2 text-sm text-blue-600' 
                        : 'text-xs text-blue-700';
                } else if (data.state === 'SUCCESS') {
                    clearInterval(window.contentGapSkuPollingInterval);
                    window.contentGapSkuPollingInterval = null;
                    handleContentGapSkuResult(data.result || data, statusDiv, actionBtn);
                } else if (data.state === 'FAILURE') {
                    clearInterval(window.contentGapSkuPollingInterval);
                    window.contentGapSkuPollingInterval = null;
                    const errorMsg = data.error || 'SKU counting failed';
                    if (statusDiv) {
                        statusDiv.textContent = `Error: ${errorMsg}`;
                        statusDiv.className = statusDiv.id === 'content-gap-sku-status-lens' 
                            ? 'mt-2 text-sm text-red-600' 
                            : 'text-xs text-red-700';
                    }
                    showNotification(errorMsg, 'error');
                    if (actionBtn) {
                        actionBtn.disabled = false;
                        actionBtn.textContent = 'Estimate SKU Counts';
                    }
                }
            } catch (error) {
                clearInterval(window.contentGapSkuPollingInterval);
                window.contentGapSkuPollingInterval = null;
                console.error('Error polling SKU count task:', error);
                if (statusDiv) {
                    statusDiv.textContent = `Error polling task: ${error.message}`;
                    statusDiv.className = statusDiv.id === 'content-gap-sku-status-lens' 
                        ? 'mt-2 text-sm text-red-600' 
                        : 'text-xs text-red-700';
                }
                if (actionBtn) {
                    actionBtn.disabled = false;
                    actionBtn.textContent = 'Estimate SKU Counts';
                }
            }
        }, 2000);
    }

    function setupContentGapPimUploadListeners() {
        const fileInput = document.getElementById('content-gap-pim-file-lens');
        const runBtn = document.getElementById('run-content-gap-sku-btn-lens');
        const statusDiv = document.getElementById('content-gap-sku-status-lens');
        const skuWrapper = document.getElementById('content-gap-sku-column-selector-lens');
        const skuSelect = document.getElementById('content-gap-sku-id-column-lens');

        if (!fileInput || !runBtn) return;

        // Reset file input and status when view loads
        fileInput.value = '';
        if (skuWrapper) skuWrapper.style.display = 'none';
        runBtn.disabled = true;

        // Update status if SKU counts already exist
        const skuCounts = window.contentGapSkuCounts || contentGapSkuCounts;
        if (skuCounts && Object.keys(skuCounts).length > 0 && statusDiv) {
            statusDiv.textContent = `SKU counts ready for ${Object.keys(skuCounts).length} keywords.`;
            statusDiv.className = 'mt-2 text-sm text-green-600';
        } else if (statusDiv) {
            statusDiv.textContent = 'Upload a PIM CSV to estimate Toolstation SKU coverage for gaps.';
            statusDiv.className = 'mt-2 text-sm text-gray-600';
        }

        fileInput.addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) {
                runBtn.disabled = true;
                return;
            }
            try {
                const text = await file.text();
                const headerLine = (text.split(/\r?\n/)[0] || '');
                const headers = headerLine.split(',').map(h => h.trim().replace(/^"|"$/g, '')).filter(Boolean);
                if (skuWrapper && skuSelect) {
                    skuSelect.innerHTML = '<option value="">Auto-detect SKU column</option>' + headers.map(h => `<option value="${escapeHtml(h)}">${escapeHtml(h)}</option>`).join('');
                    skuWrapper.classList.remove('hidden');
                }
                runBtn.disabled = false;
                if (statusDiv) {
                    statusDiv.textContent = 'Ready to estimate SKU counts';
                    statusDiv.className = 'mt-2 text-sm text-gray-600';
                }
            } catch (error) {
                console.error('Error reading PIM file:', error);
                showNotification('Error reading PIM file. Please check the CSV and try again.', 'error');
                runBtn.disabled = true;
            }
        });

        runBtn.addEventListener('click', async () => {
            const file = fileInput.files[0];
            if (!file) {
                showNotification('Please select a PIM CSV file first.', 'error');
                return;
            }

            const terms = getContentGapSkuTerms();
            if (!terms.length) {
                showNotification('No keyword gaps available to estimate SKU counts.', 'error');
                return;
            }

            const skuColumn = skuSelect ? skuSelect.value : '';
            const formData = new FormData();
            formData.append('pimFile', file);
            formData.append('terms', JSON.stringify(terms));
            if (skuColumn) {
                formData.append('skuIdColumn', skuColumn);
            }

            runBtn.disabled = true;
            runBtn.textContent = 'Estimating...';
            if (statusDiv) {
                statusDiv.textContent = 'Uploading and estimating SKU counts...';
                statusDiv.className = statusDiv.id === 'content-gap-sku-status-lens' 
                    ? 'mt-2 text-sm text-blue-600' 
                    : 'text-xs text-blue-700';
            }

            const protocol = window.location.protocol || 'http:';
            const hostname = window.location.hostname || '127.0.0.1';
            let lastError = null;
            let immediateResult = null;

            for (let port = 5000; port <= 5010; port++) {
                try {
                    const apiUrl = `${protocol}//${hostname}:${port}/api/pim/sku_counts`;
                    const response = await fetch(apiUrl, {
                        method: 'POST',
                        headers: {
                            'X-API-KEY': API_KEY
                        },
                        body: formData,
                        signal: AbortSignal.timeout(360000)
                    });

                    const contentType = response.headers.get('content-type') || '';
                    if (response.status === 202 && contentType.includes('application/json')) {
                        const taskData = await response.json();
                        if (taskData.task_id) {
                            startContentGapSkuPolling(hostname, port, taskData.task_id, statusDiv, runBtn);
                            return;
                        }
                    } else if (response.ok && contentType.includes('application/json')) {
                        immediateResult = await response.json();
                        break;
                    } else {
                        let errorMessage = `Server error on port ${port} (Status: ${response.status})`;
                        try {
                            if (contentType.includes('application/json')) {
                                const errorData = await response.json();
                                errorMessage = errorData.error || errorMessage;
                            } else {
                                const text = await response.text();
                                errorMessage = text.substring(0, 200) || errorMessage;
                            }
                        } catch (_) {
                            // ignore parse errors
                        }
                        lastError = new Error(errorMessage);
                        continue;
                    }
                } catch (error) {
                    lastError = error;
                    continue;
                }
            }

            if (!immediateResult) {
                const errMessage = lastError ? lastError.message : 'Could not reach SKU counting endpoint.';
                showNotification(errMessage, 'error');
                if (statusDiv) {
                    statusDiv.textContent = `Error: ${errMessage}`;
                    statusDiv.className = statusDiv.id === 'content-gap-sku-status-lens' 
                        ? 'mt-2 text-sm text-red-600' 
                        : 'text-xs text-red-700';
                }
                runBtn.disabled = false;
                runBtn.textContent = 'Estimate SKU Counts';
                return;
            }

            handleContentGapSkuResult(immediateResult, statusDiv, runBtn);
        });
    }

    function rerenderCurrentContentGapLens() {
        const container = document.querySelector('[data-report-title]');
        if (!container) return;
        const title = container.dataset.reportTitle || '';

        if (title.includes('Content Gaps | Individual Keywords')) {
            renderKeywordGapAnalysisView();
        } else if (title.includes('Content Gaps | Keyword Groups')) {
            const activeScopeBtn = document.querySelector('.scope-toggle-btn.active');
            const scope = activeScopeBtn && activeScopeBtn.dataset.scope ? activeScopeBtn.dataset.scope : 'core';
            renderTopicGapAnalysisView(scope);
        }
    }

    function renderKeywordGapAnalysisView() {
        const { keywordGapReport, hasOnsiteData, onsiteDateRange } = analysisResults;
        let transformedData = transformDataForTimeframe(keywordGapReport, tableState.timeframe);
        const skuCounts = window.contentGapSkuCounts || contentGapSkuCounts;
        const hasSkuCounts = skuCounts && Object.keys(skuCounts).length > 0;

        const dateSuffix = onsiteDateRange ? ` (${onsiteDateRange})` : '';
        const onsiteSearchesHeader = `On-Site Searches${dateSuffix}`;
        const opportunityScoreHeader = 'Opportunity Score';
        const staticOnsiteSearchesKey = 'On-Site Searches'; // The key name from Python

        let headers = ['Keyword', 'Monthly Google Searches', '# Ranking Competitors', 'Top Ranking Competitor', 'Top Competitor URL', 'Highest Competitor Rank', 'Top Competitor Monthly Organic Traffic'];
        
        if (hasOnsiteData) {
            // Add the dynamic header name to our list of headers
            headers.push(onsiteSearchesHeader, opportunityScoreHeader);
            
            // RENAME THE KEY in the data to match the dynamic header name
            transformedData.forEach(row => {
                if (row.hasOwnProperty(staticOnsiteSearchesKey)) {
                    row[onsiteSearchesHeader] = row[staticOnsiteSearchesKey];
                    delete row[staticOnsiteSearchesKey];
                }
            });
        }
        if (hasSkuCounts) {
            headers.push('Estimated TS SKU Count');
        }

        const displayHeaders = updateHeadersForTimeframe(headers, tableState.timeframe);

        const displayData = transformedData.map(row => {
            const newRow = {...row};
            const urlHeader = 'Top Competitor URL';
            const urlKeyInRow = Object.keys(newRow).find(k => k.includes(urlHeader));
            if (urlKeyInRow && newRow[urlKeyInRow]) {
                newRow[urlKeyInRow] = `<a href="${newRow[urlKeyInRow]}" target="_blank" class="text-blue-600 hover:underline break-all">${newRow[urlKeyInRow]}</a>`;
            }
            if (hasSkuCounts) {
                const keyword = row['Keyword'];
                const skuEntry = keyword && skuCounts ? skuCounts[keyword] : null;
                const skuCountValue = typeof skuEntry === 'object' && skuEntry !== null
                    ? (skuEntry.count ?? skuEntry.sku_count ?? skuEntry.skuCount ?? 0)
                    : (skuEntry ?? 0);
                newRow['Estimated TS SKU Count'] = skuCountValue;
            }
            return newRow;
        });

        const subtitle = 'Specific keywords where competitors rank, but you do not. Prioritised by Opportunity Score.';
        const scoreDescription = `The <strong>Opportunity Score</strong> is a 0-100 metric calculated by weighting on-site search volume (40%), Google search volume (20%), and the top competitor's traffic (40%) to prioritise your most valuable content gaps.`;
        const description = GAP_ANALYSIS_CAVEAT + (hasOnsiteData ? `<br><br>${scoreDescription}`: '');
        ui.resultsContainer.innerHTML = createReportContainer('Content Gaps | Individual Keywords', subtitle, '', description);

        const defaultSortKeyFromHeaders = hasOnsiteData ? opportunityScoreHeader : headers[1];
        const defaultSortKey = updateHeadersForTimeframe([defaultSortKeyFromHeaders], tableState.timeframe)[0];
        initializeTable(displayData, displayHeaders, defaultSortKey, 'Keyword');
    }

    function renderTopicGapAnalysisView(scope = 'core') {
        const reportData = (scope === 'core') ? analysisResults.coreTopicGapReport : analysisResults.topicGapReport;
        let transformedData = transformDataForTimeframe(reportData, tableState.timeframe);
        const skuCounts = window.contentGapSkuCounts || contentGapSkuCounts;
        const hasSkuCounts = skuCounts && Object.keys(skuCounts).length > 0;
        const keywordMap = scope === 'core' ? analysisResults.coreTopicKeywordMap : analysisResults.topicKeywordMap;
        const topicSkuCounts = {};
        const topicSkuIdsMap = {};
        const groupSkuIdsMap = {};

        if (hasSkuCounts && keywordMap) {
            Object.entries(keywordMap).forEach(([topicId, keywords]) => {
                const uniqueSkuIds = new Set();
                const idKeywordMap = {};
                let fallbackSum = 0;

                (keywords || []).forEach(kw => {
                    const entry = skuCounts[kw];
                    if (entry && typeof entry === 'object') {
                        if (Array.isArray(entry.sku_ids)) {
                            entry.sku_ids.forEach(id => {
                                const idStr = (id !== null && id !== undefined) ? String(id).trim() : '';
                                if (idStr) {
                                    uniqueSkuIds.add(idStr);
                                    if (!idKeywordMap[idStr]) {
                                        idKeywordMap[idStr] = kw;
                                    }
                                }
                            });
                        }
                        const entryCount = entry.count ?? entry.sku_count ?? entry.skuCount ?? 0;
                        fallbackSum += entryCount;
                    } else if (entry !== undefined && entry !== null) {
                        fallbackSum += Number(entry) || 0;
                    }
                });

                topicSkuCounts[topicId] = uniqueSkuIds.size > 0 ? uniqueSkuIds.size : fallbackSum;
                topicSkuIdsMap[topicId] = Array.from(uniqueSkuIds);
                contentGapTopicSkuIdKeywordMap[topicId] = idKeywordMap;
            });
            // Build group-level map keyed by Keyword Group label
            transformedData.forEach(row => {
                const topicId = row['TopicID'];
                const groupName = row['Keyword Group'];
                const ids = topicSkuIdsMap[topicId] || [];
                const idKwMap = contentGapTopicSkuIdKeywordMap[topicId] || {};
                if (groupName) {
                    const current = groupSkuIdsMap[groupName] || new Set();
                    const currentKwMap = contentGapGroupSkuIdKeywordMap[groupName] || {};
                    ids.forEach(id => {
                        current.add(id);
                        if (!currentKwMap[id] && idKwMap[id]) {
                            currentKwMap[id] = idKwMap[id];
                        }
                    });
                    groupSkuIdsMap[groupName] = current;
                    contentGapGroupSkuIdKeywordMap[groupName] = currentKwMap;
                }
            });
            // Persist globally for exports
            contentGapTopicSkuIds = topicSkuIdsMap;
            contentGapGroupSkuIds = Object.fromEntries(Object.entries(groupSkuIdsMap).map(([k, v]) => [k, Array.from(v)]));
            window.contentGapTopicSkuIds = contentGapTopicSkuIds;
            window.contentGapGroupSkuIds = contentGapGroupSkuIds;
            window.contentGapTopicSkuIdKeywordMap = contentGapTopicSkuIdKeywordMap;
            window.contentGapGroupSkuIdKeywordMap = contentGapGroupSkuIdKeywordMap;
        }

        const { hasOnsiteData, onsiteDateRange } = analysisResults;
        const dateSuffix = onsiteDateRange ? ` (${onsiteDateRange})` : '';
        
        const opportunityScoreHeader = `Opportunity Score`;
        const staticOnsiteSearchesKey = `Total On-Site Searches`;
        const totalOnsiteSearchesHeader = `Total On-Site Searches${dateSuffix}`;

        let headers = ['Keyword Group', 'TopicID', 'Total Monthly Google Searches', 'Total Competitor Monthly Organic Traffic', 'Gap Keyword Count', 'Competitor Avg. Rank'];
        
        if(hasOnsiteData) {
            headers = ['Keyword Group', 'TopicID', opportunityScoreHeader, 'Total Monthly Google Searches', totalOnsiteSearchesHeader, 'Total Competitor Monthly Organic Traffic', 'Gap Keyword Count', 'Competitor Avg. Rank'];
            
            const keyInData = updateHeadersForTimeframe([staticOnsiteSearchesKey], tableState.timeframe)[0];
            const keyForDisplay = updateHeadersForTimeframe([totalOnsiteSearchesHeader], tableState.timeframe)[0];

            transformedData.forEach(row => {
                if (row.hasOwnProperty(keyInData)) {
                    row[keyForDisplay] = row[keyInData];
                    if (keyInData !== keyForDisplay) {
                       delete row[keyInData];
                    }
                }
            });
        }
        if (hasSkuCounts) {
            headers.push('Estimated TS SKU Count');
        }
        const displayHeaders = updateHeadersForTimeframe(headers, tableState.timeframe);

        const displayData = transformedData.map(row => {
            const newRow = {...row};
            const gapCountKey = Object.keys(newRow).find(k => k.includes('Gap Keyword Count'));
            if (gapCountKey) {
                newRow[gapCountKey] = `<button class="text-blue-600 hover:underline view-keywords-btn" data-map-source="${scope}" data-topic-id="${row['TopicID']}">${row[gapCountKey]}</button>`;
            }
            if (hasSkuCounts) {
                newRow['Estimated TS SKU Count'] = topicSkuCounts[row['TopicID']] ?? null;
            }
            return newRow;
        });

        const subtitle = "Aggregated topics where you have visibility gaps against competitors. 'Core' includes only keywords ranking in the Top 20 for competitors.";
        const topicDescription = `<b>Note:</b> Metrics shown are aggregated from <em>all</em> keywords in the topic group. The group name is generated from the top 3 keywords with the highest Opportunity Score.<br><br>The <strong>Competitor Avg. Rank</strong> is the average ranking position of all competitors for the keywords within that topic group, considering only keywords for which you have no ranking.`;
        const fullDescription = GAP_ANALYSIS_CAVEAT + `<br><br>` + topicDescription;
        const scopeToggle = `<div class="mb-4"><span class="text-sm font-semibold mr-2">Topic Scope:</span><button data-scope="core" class="scope-toggle-btn text-xs font-semibold py-1 px-3 rounded-l-md ${scope === 'core' ? 'active' : ''}">Core</button><button data-scope="full" class="scope-toggle-btn text-xs font-semibold py-1 px-3 rounded-r-md ${scope === 'full' ? 'active' : ''}">Full</button></div>`;
        ui.resultsContainer.innerHTML = createReportContainer('Content Gaps | Keyword Groups', subtitle, scopeToggle, fullDescription);
        
        const finalTableHeaders = displayHeaders.filter(h => h !== 'TopicID'); 
        const dataForTable = displayData.map(row => { 
            const newRow = {...row}; 
            delete newRow.TopicID;
            return newRow; 
        });
        
        const defaultSortKeyFromHeaders = hasOnsiteData ? opportunityScoreHeader : 'Total Monthly Google Searches';
        const defaultSortKey = updateHeadersForTimeframe([defaultSortKeyFromHeaders], tableState.timeframe)[0];

        initializeTable(dataForTable, finalTableHeaders, defaultSortKey, 'Keyword Group');
    }

    function renderKeywordThreatsAnalysisView() {
        const { keywordThreatsReport } = analysisResults;
        const transformedData = transformDataForTimeframe(keywordThreatsReport, tableState.timeframe);
        
        const headers = ['Keyword', 'Monthly Google Searches', 'Our Rank', 'Our URL', 'Our Monthly Organic Traffic', 'Best Competitor', 'Best Competitor Rank', 'Best Competitor URL', 'Best Competitor Monthly Organic Traffic', 'Monthly Traffic Growth Opportunity'];
        const displayHeaders = updateHeadersForTimeframe(headers, tableState.timeframe);
        
        const displayData = transformedData.map(row => {
            const newRow = {};
            displayHeaders.forEach(h => newRow[h] = row[h]);
            newRow['Our URL'] = `<a href="${row['Our URL']}" target="_blank" class="text-blue-600 hover:underline break-all">${row['Our URL']}</a>`;
            newRow['Best Competitor URL'] = `<a href="${row['Best Competitor URL']}" target="_blank" class="text-blue-600 hover:underline break-all">${row['Best Competitor URL']}</a>`;
            return newRow;
        });

        const subtitle = "Keywords where competitors outrank you, prioritised by the potential traffic gain.";
        ui.resultsContainer.innerHTML = createReportContainer('Competitive Opportunities | Individual Keywords', subtitle);
        initializeTable(displayData, displayHeaders, displayHeaders[9], 'Keyword');
    }

    function renderTopicThreatsAnalysisView(scope = 'core') {
        const reportData = (scope === 'core') ? analysisResults.coreTopicThreatsReport : analysisResults.topicThreatsReport;
        const transformedData = transformDataForTimeframe(reportData, tableState.timeframe);
        const mapSource = (scope === 'core') ? 'core-threats' : 'topic-threats';
        
        const headers = ['Keyword Group', 'TopicID', 'Keyword Count', 'Total Monthly Google Searches', 'Avg Our Rank', 'Total Our Monthly Traffic', 'Avg Best Competitor Rank', 'Total Best Competitor Monthly Traffic', 'Total Monthly Traffic Growth Opportunity'];
        const displayHeaders = updateHeadersForTimeframe(headers, tableState.timeframe);

        const displayData = transformedData.map(row => {
            const newRow = {};
            displayHeaders.forEach(h => newRow[h] = row[h]);
            newRow['Keyword Count'] = `<button class="text-blue-600 hover:underline view-keywords-btn" data-map-source="${mapSource}" data-topic-id="${row['TopicID']}">${row['Keyword Count']}</button>`;
            return newRow;
        });

        const subtitle = "Topic groups where competitors outrank you, prioritised by the total potential traffic gain. 'Core' shows topics where the competitor is in the Top 10.";
        const threatsDescription = `<b>Note:</b> Metrics are aggregated from keywords where a competitor outranks you. <b>Avg Our Rank</b> is your average position for these keywords, and <b>Avg Best Competitor Rank</b> is the top competitor's average position for the same set of keywords.`;
        const scopeToggle = `<div class="mb-4"><span class="text-sm font-semibold mr-2">Threat Scope:</span><button data-scope="core" class="scope-toggle-btn text-xs font-semibold py-1 px-3 rounded-l-md ${scope === 'core' ? 'active' : ''}">Core (Comp Rank <= 10)</button><button data-scope="full" class="scope-toggle-btn text-xs font-semibold py-1 px-3 rounded-r-md ${scope === 'full' ? 'active' : ''}">Full</button></div>`;
        
        ui.resultsContainer.innerHTML = createReportContainer('Competitive Opportunities | Keyword Groups', subtitle, scopeToggle, threatsDescription);
        
        const finalTableHeaders = displayHeaders.filter(h => h !== 'TopicID'); 
        const dataForTable = displayData.map(row => { 
            const newRow = {...row}; 
            delete newRow.TopicID;
            return newRow; 
        });

        initializeTable(dataForTable, finalTableHeaders, finalTableHeaders[7], 'Keyword Group');
    }
    
    function renderKeywordMarketShareView() {
        const { keywordMarketShareReport, ourDomain, competitorDomains, columnMap } = analysisResults;
        const transformedData = transformDataForTimeframe(keywordMarketShareReport, tableState.timeframe);
        
        const allDomains = [ourDomain, ...competitorDomains];
        const keywordColName = columnMap.keywordCol || 'Keyword';
        const headers = [keywordColName, 'Total Monthly Google Traffic', ...allDomains];
        const displayHeaders = updateHeadersForTimeframe(headers, tableState.timeframe);
        
        const displayData = transformedData.map(row => {
            const newRow = { 'Keyword': row['Keyword'] };
            displayHeaders.forEach(h => newRow[h] = row[h]);
            return newRow;
        });

        const subtitle = "Estimated traffic share for each domain on a per-keyword basis.";
        ui.resultsContainer.innerHTML = createReportContainer('Market Share | Individual Keywords', subtitle);
        initializeTable(displayData, displayHeaders, displayHeaders[1], 'Keyword', allDomains);
    }

    function renderGroupMarketShareView(scope = 'core') {
        const { ourDomain, competitorDomains } = analysisResults;
        const reportData = scope === 'core' ? analysisResults.coreGroupMarketShareReport : analysisResults.groupMarketShareReport;
        const transformedData = transformDataForTimeframe(reportData, tableState.timeframe);
        const mapSource = scope === 'core' ? 'market-share-core-group' : 'market-share-group';

        const allDomains = [ourDomain, ...competitorDomains];
        const headers = ['Keyword Group', 'Keyword Count', 'Total Monthly Google Traffic', ...allDomains];
        const displayHeaders = updateHeadersForTimeframe(headers, tableState.timeframe);

        const displayData = transformedData.map(row => {
            const newRow = {};
            displayHeaders.forEach(h => newRow[h] = row[h]);
            newRow['Keyword Count'] = `<button class="text-blue-600 hover:underline view-keywords-btn" data-map-source="${mapSource}" data-keyword-group="${row['Keyword Group']}">${row['Keyword Count']}</button>`;
            return newRow;
        });
        
        const subtitle = "Estimated traffic share for each domain within a keyword group. 'Core' includes only keywords where a competitor ranks in the Top 20.";
        const scopeToggle = `<div class="mb-4"><span class="text-sm font-semibold mr-2">Scope:</span><button data-scope="core" class="scope-toggle-btn text-xs font-semibold py-1 px-3 rounded-l-md ${scope === 'core' ? 'active' : ''}">Core (Rank <= 20)</button><button data-scope="full" class="scope-toggle-btn text-xs font-semibold py-1 px-3 rounded-r-md ${scope === 'full' ? 'active' : ''}">Full</button></div>`;

        ui.resultsContainer.innerHTML = createReportContainer('Market Share | Keyword Groups', subtitle, scopeToggle);
        initializeTable(displayData, displayHeaders, displayHeaders[2], 'Keyword Group', allDomains);
    }

    function renderCategoryOverhaulMatrixView() {
        const { categoryOverhaulMatrixReport, hasOnsiteData } = analysisResults;
        
        if (!categoryOverhaulMatrixReport || categoryOverhaulMatrixReport.length === 0) {
            ui.resultsContainer.innerHTML = createReportContainer('Category Overhaul Matrix', 'No data available for this report.');
            return;
        }
        tableState.activeLens = 'category-overhaul';
        tableState.rowEditState = null;
        const baseHeaders = Object.keys(categoryOverhaulMatrixReport[0] || {});
        
        // Build list of columns to exclude from aggregation (hidden columns)
        // Note: Entities column no longer exists (excluded at data load), only Features
        const excludeFromAggregation = [];
        if (tableState.hideFeatures) {
            excludeFromAggregation.push('Features', 'Discovered Features');
        }
        
        // Re-aggregate data excluding hidden columns (rows differing only in hidden columns will merge)
        const modifiedData = applyOverridesAndMerge(categoryOverhaulMatrixReport, baseHeaders, hasOnsiteData, excludeFromAggregation);
        const transformedData = transformDataForTimeframe(modifiedData, tableState.timeframe);

        const allKeys = new Set();
        transformedData.forEach(row => { Object.keys(row).forEach(key => allKeys.add(key)); });
        
        const preferredOrder = ['Category Mapping', 'Derived Facets', 'Sub Type'];
        const endColumnsBases = ['Monthly Organic Traffic', 'Total Monthly Google Searches', 'Total On-Site Searches', 'KeywordDetails'];
        const endColumns = updateHeadersForTimeframe(endColumnsBases, tableState.timeframe);

        const finalHeaders = [
            ...preferredOrder.filter(h => allKeys.has(h)),
            ...Array.from(allKeys).filter(h => !preferredOrder.includes(h) && !endColumns.includes(h)).sort(),
            ...endColumns.filter(h => allKeys.has(h))
        ];

        const subtitle = "Analyse competitor taxonomy to find high-value category and facet opportunities.";
        const explainer = `
            <div class="text-sm text-gray-600 bg-blue-50 border border-blue-200 p-3 rounded-md mb-4">
                <b>How this report works:</b> This matrix analyzes the architecture of the single highest-ranking URL for every keyword in your dataset to reveal traffic opportunities.
                <ul class="list-disc list-inside mt-2">
                    <li>Each row represents a unique combination of categories and facets found on top-ranking pages. Click the ▶ button to see the keywords driving each row.</li>
                    <li>Use the "Manual Overrides" section to merge or move facet values in real-time. Changes will be reflected in exports and the Facet Potential view.</li>
                </ul>
            </div>`;
        
        const customContent = `
            <div class="flex flex-wrap gap-4 items-center">
                <div class="flex items-center">
                    <input type="checkbox" id="hide-zero-traffic-toggle" class="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500">
                    <label for="hide-zero-traffic-toggle" class="ml-2 block text-sm text-gray-900">Hide rows with 0 traffic</label>
                </div>
                <div class="flex items-center">
                    <input type="checkbox" id="hide-features-column" class="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" ${tableState.hideFeatures ? 'checked' : ''}>
                    <label for="hide-features-column" class="ml-2 block text-sm text-gray-900">Hide Features column</label>
                </div>
                <div class="flex items-center">
                    <input type="checkbox" id="hide-zero-value-columns" class="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" ${tableState.hideZeroValueColumns ? 'checked' : ''}>
                    <label for="hide-zero-value-columns" class="ml-2 block text-sm text-gray-900">Hide Columns With 0 Values</label>
                </div>
            </div>`;
        
        ui.resultsContainer.innerHTML = createReportContainer('Category Overhaul Matrix', subtitle, customContent, explainer);
        const zeroTrafficToggle = document.getElementById('hide-zero-traffic-toggle');
        if (zeroTrafficToggle) zeroTrafficToggle.checked = tableState.hideZeroTraffic;
        
        // Filter headers based on column visibility state
        let displayHeaders = [...finalHeaders];
        if (tableState.hideFeatures) {
            displayHeaders = displayHeaders.filter(h => h !== 'Features' && h !== 'Discovered Features');
        }
        
        // Filter out columns with all blank/0 values if the option is enabled
        if (tableState.hideZeroValueColumns && transformedData.length > 0) {
            displayHeaders = displayHeaders.filter(header => {
                // Always keep certain important columns
                const keepColumns = ['Category Mapping', 'Derived Facets', 'Sub Type', 'KeywordDetails'];
                if (keepColumns.includes(header) || header.includes('Traffic') || header.includes('Searches')) {
                    return true;
                }
                
                // Check if all values in this column are blank/0
                const hasNonBlankValue = transformedData.some(row => {
                    const value = row[header];
                    // Consider a value as non-blank if it's not null, undefined, empty string, or 0
                    return value !== null && value !== undefined && value !== '' && value !== 0;
                });
                
                return hasNonBlankValue;
            });
        }
        
        const defaultSortKey = displayHeaders.find(h => h.includes('Organic Traffic'));
        initializeTable(transformedData, displayHeaders, defaultSortKey, 'Category Mapping');
        
        // Add event listener for column visibility toggle
        document.getElementById('hide-features-column')?.addEventListener('change', (e) => {
            tableState.hideFeatures = e.target.checked;
            renderCategoryOverhaulMatrixView();
        });
        
        // Add event listener for hide zero value columns toggle
        document.getElementById('hide-zero-value-columns')?.addEventListener('change', (e) => {
            tableState.hideZeroValueColumns = e.target.checked;
            renderCategoryOverhaulMatrixView();
        });
        tableState.hideZeroTraffic = false; 
        renderOverridesUI(baseHeaders.filter(h => h !== 'KeywordDetails'));
    }

    function renderInteractiveCategoryMatrixView() {
        const { categoryOverhaulMatrixReport, hasOnsiteData } = analysisResults;

        if (!categoryOverhaulMatrixReport || categoryOverhaulMatrixReport.length === 0) {
            ui.resultsContainer.innerHTML = createReportContainer('Interactive Matrix Editor', 'No data available for this report.');
            return;
        }

        tableState.activeLens = 'interactive-matrix';
        tableState.rowEditState = null;
        const baseHeaders = Object.keys(categoryOverhaulMatrixReport[0] || {});
        const excludeFromAggregation = [];
        if (tableState.hideFeatures) {
            excludeFromAggregation.push('Features', 'Discovered Features');
        }

        const modifiedData = applyOverridesAndMerge(categoryOverhaulMatrixReport, baseHeaders, hasOnsiteData, excludeFromAggregation);
        const transformedData = transformDataForTimeframe(modifiedData, tableState.timeframe);

        const allKeys = new Set();
        transformedData.forEach(row => { Object.keys(row).forEach(key => allKeys.add(key)); });

        const preferredOrder = ['Category Mapping', 'Derived Facets', 'Sub Type'];
        const endColumnsBases = ['Monthly Organic Traffic', 'Total Monthly Google Searches', 'Total On-Site Searches', 'KeywordDetails'];
        const endColumns = updateHeadersForTimeframe(endColumnsBases, tableState.timeframe);

        const finalHeaders = [
            ...preferredOrder.filter(h => allKeys.has(h)),
            ...Array.from(allKeys).filter(h => !preferredOrder.includes(h) && !endColumns.includes(h)).sort(),
            ...endColumns.filter(h => allKeys.has(h))
        ];

        const subtitle = "Edit specific matrix rows and add conditional overrides without leaving the table.";
        const customContent = `
            <div class="flex flex-wrap gap-4 items-center">
                <div class="flex items-center">
                    <input type="checkbox" id="hide-zero-traffic-toggle" class="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500">
                    <label for="hide-zero-traffic-toggle" class="ml-2 block text-sm text-gray-900">Hide rows with 0 traffic</label>
                </div>
                <div class="flex items-center">
                    <input type="checkbox" id="hide-features-column" class="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" ${tableState.hideFeatures ? 'checked' : ''}>
                    <label for="hide-features-column" class="ml-2 block text-sm text-gray-900">Hide Features column</label>
                </div>
                <div class="flex items-center">
                    <input type="checkbox" id="hide-zero-value-columns" class="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" ${tableState.hideZeroValueColumns ? 'checked' : ''}>
                    <label for="hide-zero-value-columns" class="ml-2 block text-sm text-gray-900">Hide Columns With 0 Values</label>
                </div>
            </div>`;
        const explainer = `
            <div class="text-sm text-gray-600 bg-blue-50 border border-blue-200 p-3 rounded-md mb-4">
                <b>Interactive Editing:</b> Select any row to create a targeted override. You can limit a change to the exact context (e.g., Category Mapping + Type combination) before applying it to the full dataset.
            </div>`;

        ui.resultsContainer.innerHTML = createReportContainer('Interactive Matrix Editor', subtitle, customContent, explainer);
        const interactiveZeroToggle = document.getElementById('hide-zero-traffic-toggle');
        if (interactiveZeroToggle) interactiveZeroToggle.checked = tableState.hideZeroTraffic;

        let displayHeaders = [...finalHeaders];
        if (tableState.hideFeatures) {
            displayHeaders = displayHeaders.filter(h => h !== 'Features' && h !== 'Discovered Features');
        }
        if (tableState.hideZeroValueColumns && transformedData.length > 0) {
            displayHeaders = displayHeaders.filter(header => {
                const keepColumns = ['Category Mapping', 'Derived Facets', 'Sub Type', 'KeywordDetails'];
                if (keepColumns.includes(header) || header.includes('Traffic') || header.includes('Searches')) {
                    return true;
                }
                const hasNonBlankValue = transformedData.some(row => {
                    const value = row[header];
                    return value !== null && value !== undefined && value !== '' && value !== 0;
                });
                return hasNonBlankValue;
            });
        }

        tableState.interactiveHeaders = displayHeaders;
        const defaultSortKey = displayHeaders.find(h => h.includes('Organic Traffic'));
        initializeTable(transformedData, displayHeaders, defaultSortKey, 'Category Mapping');

        document.getElementById('hide-features-column')?.addEventListener('change', (e) => {
            tableState.hideFeatures = e.target.checked;
            renderInteractiveCategoryMatrixView();
        });
        document.getElementById('hide-zero-value-columns')?.addEventListener('change', (e) => {
            tableState.hideZeroValueColumns = e.target.checked;
            renderInteractiveCategoryMatrixView();
        });

        renderOverridesUI(baseHeaders.filter(h => h !== 'KeywordDetails'));
        let editorContainer = document.getElementById('interactive-row-editor');
        if (!editorContainer) {
            const manualContainer = document.getElementById('manual-overrides-container');
            if (manualContainer) {
                manualContainer.insertAdjacentHTML('afterend', `<div id="interactive-row-editor" class="mb-6 border rounded-lg p-4 bg-white shadow-sm"><p class="text-sm text-gray-500">Select a row below to begin editing.</p></div>`);
            }
        } else {
            editorContainer.innerHTML = `<p class="text-sm text-gray-500">Select a row below to begin editing.</p>`;
        }
    }

    function getEditableColumns(headers = []) {
        if (!Array.isArray(headers)) return [];
        const excludedSubstrings = ['Traffic', 'Searches', 'KeywordDetails', 'FacetValueDetails', 'Keyword Count', 'Monthly Google'];
        return headers.filter(h => {
            if (!h) return false;
            if (h === 'KeywordDetails' || h === 'FacetValueDetails') return false;
            if (excludedSubstrings.some(sub => h.includes(sub))) return false;
            if (isFeatureColumn(h)) return false;
            return true;
        });
    }

    function getRowById(rowId) {
        if (rowId === undefined || rowId === null) return null;
        return (tableState.fullData || []).find(row => row && row.__rowId === Number(rowId));
    }

    function splitCellValues(value) {
        if (value === null || value === undefined || String(value).trim() === '') {
            return [{ label: '(Blank)', value: '__ROW_BLANK__' }];
        }
        return String(value).split('|').map(v => v.trim()).filter(Boolean).map(v => ({ label: v, value: v }));
    }

    function renderInteractiveRowEditor(rowId) {
        const row = getRowById(rowId);
        const editorContainer = document.getElementById('interactive-row-editor');
        if (!row || !editorContainer) return;

        const editableColumns = getEditableColumns(tableState.interactiveHeaders);
        if (editableColumns.length === 0) {
            editorContainer.innerHTML = `<p class="text-sm text-gray-500">No editable columns available for this row.</p>`;
            return;
        }

        if (!editableColumns.includes('Category Mapping') && row.hasOwnProperty('Category Mapping')) {
            editableColumns.unshift('Category Mapping');
        }

        const defaultColumn = editableColumns.includes('Type') ? 'Type' : editableColumns[0];
        const valueOptions = splitCellValues(row[defaultColumn]);
        const targetColumns = editableColumns.filter(col => col !== defaultColumn);

        const conditionColumns = editableColumns.filter(col => {
            const cellVal = row[col];
            return cellVal !== undefined && cellVal !== null && String(cellVal).trim() !== '';
        });
        if (!conditionColumns.includes('Category Mapping') && row['Category Mapping']) {
            conditionColumns.unshift('Category Mapping');
        }

        tableState.rowEditState = { rowId, row, editableColumns };

        const conditionHtml = conditionColumns.length === 0
            ? '<p class="text-xs text-gray-500">No contextual columns available for conditions.</p>'
            : conditionColumns.map(col => {
                const rawVal = row[col];
                const displayVal = (rawVal === null || rawVal === undefined || String(rawVal).trim() === '') ? '(Blank)' : rawVal;
                const checkedAttr = col === 'Category Mapping' ? 'checked' : '';
                const conditionValue = (rawVal === null || rawVal === undefined || String(rawVal).trim() === '') ? '' : String(rawVal).trim();
                return `<label class="flex items-center text-sm text-gray-700 space-x-2">
                    <input type="checkbox" class="row-edit-condition h-4 w-4 text-blue-600" value="${col}" data-condition-value="${escapeHtml(conditionValue)}" ${checkedAttr}>
                    <span>${col}: <b>${escapeHtml(displayVal)}</b></span>
                </label>`;
            }).join('');

        editorContainer.innerHTML = `
            <div class="flex justify-between items-center mb-4">
                <div>
                    <h3 class="text-lg font-semibold">Editing Row</h3>
                    <p class="text-xs text-gray-500">Category Mapping: <b>${escapeHtml(row['Category Mapping'] || '(Blank)')}</b></p>
                </div>
                <button id="close-row-editor" class="text-xs text-red-600 hover:text-red-800 font-semibold">Close</button>
            </div>
            <form id="row-edit-form" data-row-id="${rowId}" class="space-y-4">
                <div class="grid md:grid-cols-2 gap-4">
                    <div>
                        <label class="block text-sm font-medium">Column to edit</label>
                        <select id="row-edit-column" class="mt-1 block w-full border rounded-md p-2">
                            ${editableColumns.map(col => `<option value="${col}" ${col === defaultColumn ? 'selected' : ''}>${col}</option>`).join('')}
                        </select>
                    </div>
                    <div>
                        <label class="block text-sm font-medium">Action</label>
                        <select id="row-edit-action" class="mt-1 block w-full border rounded-md p-2">
                            <option value="change">Change value</option>
                            <option value="move">Move to column</option>
                            <option value="remove">Remove rows with this value</option>
                        </select>
                    </div>
                </div>
                <div>
                    <label class="block text-sm font-medium">Select value</label>
                    <select id="row-edit-value" class="mt-1 block w-full border rounded-md p-2">
                        ${valueOptions.map(opt => `<option value="${opt.value}">${escapeHtml(opt.label)}</option>`).join('')}
                    </select>
                </div>
                <div id="row-edit-new-value-group">
                    <label class="block text-sm font-medium">New value</label>
                    <input type="text" id="row-edit-new-value" class="mt-1 block w-full border rounded-md p-2" placeholder="Enter replacement value">
                </div>
                <div id="row-edit-target-column-group" class="hidden">
                    <label class="block text-sm font-medium">Target column</label>
                    <select id="row-edit-target-column" class="mt-1 block w-full border rounded-md p-2">
                        <option value="">Select column</option>
                        ${targetColumns.map(col => `<option value="${col}">${col}</option>`).join('')}
                    </select>
                </div>
                <div id="row-edit-move-mode-group" class="hidden">
                    <label class="block text-sm font-medium">Move mode</label>
                    <select id="row-edit-move-mode" class="mt-1 block w-full border rounded-md p-2">
                        <option value="replace">Replace target value</option>
                        <option value="append">Append to target value</option>
                    </select>
                </div>
                <div>
                    <label class="block text-sm font-medium mb-2">Limit this rule to rows where:</label>
                    <div class="space-y-2">${conditionHtml}</div>
                </div>
                <div class="flex justify-end gap-3">
                    <button type="submit" class="px-4 py-2 bg-blue-600 text-white rounded-md text-sm font-semibold hover:bg-blue-700">Apply edit</button>
                </div>
            </form>
        `;

        updateRowEditorActionVisibility('change');
    }

    function updateRowEditorValueOptions(column) {
        if (!tableState.rowEditState) return;
        const row = tableState.rowEditState.row;
        const valueSelect = document.getElementById('row-edit-value');
        const targetColumnSelect = document.getElementById('row-edit-target-column');
        if (!row || !valueSelect) return;
        const options = splitCellValues(row[column]);
        valueSelect.innerHTML = options.map(opt => `<option value="${opt.value}">${escapeHtml(opt.label)}</option>`).join('');
        if (targetColumnSelect) {
            const possibleTargets = tableState.rowEditState.editableColumns.filter(col => col !== column);
            targetColumnSelect.innerHTML = `<option value="">Select column</option>${possibleTargets.map(col => `<option value="${col}">${col}</option>`).join('')}`;
        }
    }

    function updateRowEditorActionVisibility(action) {
        const newValueGroup = document.getElementById('row-edit-new-value-group');
        const targetColumnGroup = document.getElementById('row-edit-target-column-group');
        const moveModeGroup = document.getElementById('row-edit-move-mode-group');
        if (!newValueGroup || !targetColumnGroup || !moveModeGroup) return;

        if (action === 'change') {
            newValueGroup.classList.remove('hidden');
            targetColumnGroup.classList.add('hidden');
            moveModeGroup.classList.add('hidden');
        } else if (action === 'move') {
            newValueGroup.classList.add('hidden');
            targetColumnGroup.classList.remove('hidden');
            moveModeGroup.classList.remove('hidden');
        } else {
            newValueGroup.classList.add('hidden');
            targetColumnGroup.classList.add('hidden');
            moveModeGroup.classList.add('hidden');
        }
    }

    function clearRowEditor() {
        const editorContainer = document.getElementById('interactive-row-editor');
        if (editorContainer) {
            editorContainer.innerHTML = `<p class="text-sm text-gray-500">Select a row below to begin editing.</p>`;
        }
        tableState.rowEditState = null;
    }

    function handleRowEditFormSubmit(form) {
        const rowId = form.dataset.rowId;
        const row = getRowById(rowId);
        if (!row) {
            showNotification('Could not locate the selected row.', 'error');
            return;
        }

        const sourceColumn = form.querySelector('#row-edit-column')?.value;
        const action = form.querySelector('#row-edit-action')?.value;
        let selectedValue = form.querySelector('#row-edit-value')?.value;
        if (!sourceColumn || !action) {
            showNotification('Please select a column and action.', 'error');
            return;
        }
        if (selectedValue === '__ROW_BLANK__') selectedValue = '';

        const conditions = {};
        form.querySelectorAll('.row-edit-condition:checked').forEach(cb => {
            const col = cb.value;
            const val = cb.dataset.conditionValue === undefined ? '' : cb.dataset.conditionValue;
            conditions[col] = val;
        });

        let newRule = null;
        if (action === 'change') {
            const newValue = form.querySelector('#row-edit-new-value')?.value?.trim();
            if (!newValue) {
                showNotification('Enter a new value to apply.', 'error');
                return;
            }
            if (hasMatchingOverride({ action: 'change', sourceColumn, value: selectedValue, newValue, conditions })) {
                showNotification('An identical change rule already exists.', 'info');
                return;
            }
            newRule = {
                action: 'change',
                sourceColumn,
                value: selectedValue,
                newValue,
                conditions
            };
        } else if (action === 'move') {
            const targetColumn = form.querySelector('#row-edit-target-column')?.value;
            const moveMode = form.querySelector('#row-edit-move-mode')?.value || 'replace';
            if (!targetColumn || targetColumn === sourceColumn) {
                showNotification('Select a different target column.', 'error');
                return;
            }
            if (hasMatchingOverride({ action: 'move', sourceColumn, value: selectedValue, targetColumn, moveMode, conditions })) {
                showNotification('An identical move rule already exists.', 'info');
                return;
            }
            newRule = {
                action: 'move',
                sourceColumn,
                targetColumn,
                value: selectedValue,
                moveMode,
                conditions
            };
        } else if (action === 'remove') {
            if (hasMatchingOverride({ action: 'remove', sourceColumn, value: selectedValue, conditions })) {
                showNotification('An identical removal rule already exists.', 'info');
                return;
            }
            newRule = {
                action: 'remove',
                sourceColumn,
                value: selectedValue,
                conditions
            };
        }

        if (!newRule) {
            showNotification('Unable to build rule from the provided inputs.', 'error');
            return;
        }

        overrideRules.push({ id: Date.now() + Math.random(), ...newRule });
        showNotification('Interactive override added.', 'success');
        renderInteractiveCategoryMatrixView();
    }

    function renderFacetPotentialAnalysisView() {
        const { categoryOverhaulMatrixReport, hasOnsiteData } = analysisResults;
        
        if (!categoryOverhaulMatrixReport || categoryOverhaulMatrixReport.length === 0) {
            ui.resultsContainer.innerHTML = createReportContainer('Facet Potential Analysis', 'No data available for this report.');
            return;
        }
        tableState.activeLens = 'facet-potential';
        tableState.rowEditState = null;

        const matrixBaseHeaders = Object.keys(categoryOverhaulMatrixReport[0] || {});
        const modifiedMatrixData = applyOverridesAndMerge(categoryOverhaulMatrixReport, matrixBaseHeaders, hasOnsiteData);
        
        const regeneratedData = generateFacetPotentialFromMatrix(modifiedMatrixData, matrixBaseHeaders, hasOnsiteData);
        const transformedData = transformDataForTimeframe(regeneratedData, tableState.timeframe);
        
        let headers = ['Category Mapping', 'Facet Type', 'Keyword Count', 'Facet Value Score', 'Monthly Organic Traffic', 'Total Monthly Google Searches'];
        if (hasOnsiteData) headers.push('Total On-Site Searches');
        
        const displayHeaders = updateHeadersForTimeframe(headers, tableState.timeframe);
        
        const subtitle = "A high-level view of which facet types are most associated with traffic and volume for each category.";
        const explainer = `<div class="text-sm text-gray-600 bg-blue-50 border border-blue-200 p-3 rounded-md mb-4">
            <b>How to use this report:</b> This analysis rolls up the detailed Category Overhaul Matrix to show you the total value of using a certain <em>type</em> of facet within a category.
            <br><br>
            <b>Note:</b> Tick the "In Product Name" box for a facet you know is part of a core product name (e.g., "iPhone" for the "Mobile Phones" category) to give it a score boost. Any manual overrides applied are also reflected here.
        </div>`;

        ui.resultsContainer.innerHTML = createReportContainer('Facet Potential Analysis', subtitle, '', explainer);
        
        const defaultSortKey = displayHeaders.find(h => h.includes('Facet Value Score'));
        initializeTable(transformedData, displayHeaders, defaultSortKey, 'Category Mapping');
        renderOverridesUI(matrixBaseHeaders.filter(h => h !== 'KeywordDetails' && h !== 'FacetValueDetails'));
    }

    function renderSmartRecommendationsView() {
        const { categoryOverhaulMatrixReport } = analysisResults;
        
        if (!categoryOverhaulMatrixReport || categoryOverhaulMatrixReport.length === 0) {
            ui.resultsContainer.innerHTML = createReportContainer(
                'Taxonomy Smart Recommendations',
                'No Category Overhaul Matrix data available.',
                '',
                'Run the Taxonomy & Architecture analysis to generate recommendations.'
            );
            const wrapper = document.getElementById('interactive-table-wrapper');
            if (wrapper) {
                wrapper.innerHTML = '<div class="p-8 text-center text-gray-500 border rounded-lg bg-gray-50">No recommendations yet.</div>';
            }
            return;
        }

        tableState.activeLens = 'smart-recommendations';
        tableState.rowEditState = null;
        const baseHeaders = Object.keys(categoryOverhaulMatrixReport[0] || {});
        // Recommendations are generated from the raw matrix data (before overrides are applied)
        smartRecommendations = buildSmartRecommendations(categoryOverhaulMatrixReport, baseHeaders);
        smartRecommendationSelections = new Set(
            [...smartRecommendationSelections].filter(id => smartRecommendations.some(rec => rec.id === id))
        );

        const subtitle = 'AI-assisted taxonomy clean-up suggestions derived from your Category Overhaul Matrix.';
        const customContent = `
            <div class="flex flex-wrap items-center gap-3">
                <span class="text-sm font-semibold text-gray-700">${smartRecommendations.length} suggestions</span>
                <span id="selected-recommendations-count" class="text-xs text-gray-500">${smartRecommendationSelections.size} selected</span>
                <button id="refresh-smart-recommendations" class="text-xs font-semibold py-1 px-3 rounded border border-gray-300 hover:bg-gray-100">Refresh</button>
                <button id="apply-selected-recommendations" class="text-xs font-semibold py-1 px-3 rounded border border-blue-300 text-blue-700 hover:bg-blue-50 ${smartRecommendationSelections.size === 0 ? 'opacity-50 cursor-not-allowed' : ''}" ${smartRecommendationSelections.size === 0 ? 'disabled' : ''}>Apply Selected</button>
            </div>`;
        const explainer = `
            <div>
                <p class="mb-2">These Smart Recommendations flag inconsistent Category Mapping labels, SKU-level noise, and other anomalies that can be fixed via the Manual Overrides engine.</p>
                <ul class="list-disc list-inside text-sm text-gray-600 space-y-1">
                    <li><strong>Normalise</strong> aligns near-duplicate values (e.g., "Sealants.Cat" → "Sealants").</li>
                    <li><strong>Cleanup</strong> suggests removing SKU-level values that only appear once or twice.</li>
                    <li><strong>Relocate</strong> spots values living in the wrong column and recommends moving them to the dominant column.</li>
                    <li>Approving a recommendation instantly adds the matching rule to Manual Overrides and updates all dependent views.</li>
                </ul>
            </div>`;

        ui.resultsContainer.innerHTML = createReportContainer('Taxonomy Smart Recommendations', subtitle, customContent, explainer);

        const manualOverrideHeaders = baseHeaders.filter(h => h !== 'KeywordDetails' && h !== 'FacetValueDetails');
        renderOverridesUI(manualOverrideHeaders);

        const searchContainer = document.getElementById('table-search-input')?.closest('.flex');
        if (searchContainer) searchContainer.classList.add('hidden');
        const timeframeContainer = ui.resultsContainer.querySelector('.scope-toggle-btn')?.parentElement;
        if (timeframeContainer) timeframeContainer.classList.add('hidden');
        const paginationWrapper = document.getElementById('pagination-controls-wrapper');
        if (paginationWrapper) {
            paginationWrapper.innerHTML = '';
            paginationWrapper.classList.add('hidden');
        }

        const recommendationCards = smartRecommendations.length > 0
            ? smartRecommendations.map(rec => {
                let actionLabel = 'Normalise';
                let actionClasses = 'bg-indigo-100 text-indigo-800';
                if (rec.action === 'remove') {
                    actionLabel = 'Cleanup';
                    actionClasses = 'bg-red-100 text-red-800';
                } else if (rec.action === 'move') {
                    actionLabel = 'Relocate';
                    actionClasses = 'bg-blue-100 text-blue-800';
                }

                let changeSummary = '';
                if (rec.action === 'change') {
                    changeSummary = `Change "<b>${escapeHtml(rec.value)}</b>" → "<b>${escapeHtml(rec.newValue)}</b>"`;
                } else if (rec.action === 'remove') {
                    changeSummary = `Delete rows where value = "<b>${escapeHtml(rec.value)}</b>"`;
                } else if (rec.action === 'move') {
                    const modeLabel = rec.moveMode === 'replace' ? 'replace' : 'append';
                    changeSummary = `Move "<b>${escapeHtml(rec.value)}</b>" to <b>${escapeHtml(rec.targetColumn)}</b> (${modeLabel})`;
                    if (rec.targetValueHint && rec.targetValueHint !== rec.value) {
                        changeSummary += `<span class="block text-xs text-gray-500">Canonical in ${escapeHtml(rec.targetColumn)}: "${escapeHtml(rec.targetValueHint)}"</span>`;
                    }
                }
                return `
                    <div class="border rounded-lg p-4 bg-white shadow-sm">
                        <div class="flex flex-col gap-3">
                            <div class="flex items-start gap-3">
                                <input type="checkbox" class="smart-rec-select mt-1 h-4 w-4 text-blue-600 border-gray-300 rounded" data-rec-id="${rec.id}" ${smartRecommendationSelections.has(rec.id) ? 'checked' : ''}>
                                <div class="flex-1 space-y-1">
                                    <div class="flex flex-wrap items-center gap-2 text-xs">
                                        <span class="uppercase tracking-wide text-gray-500">${escapeHtml(rec.sourceColumn)}</span>
                                        <span class="px-2 py-0.5 rounded-full ${actionClasses}">${actionLabel}</span>
                                        <span class="px-2 py-0.5 rounded-full bg-gray-100 text-gray-700">Confidence ${rec.confidence}%</span>
                                        <span class="px-2 py-0.5 rounded-full bg-gray-100 text-gray-700">${rec.affectedRows} affected row${rec.affectedRows === 1 ? '' : 's'}</span>
                                    </div>
                                    <p class="font-semibold text-gray-900">${changeSummary}</p>
                                    <p class="text-sm text-gray-600">${escapeHtml(rec.reason)}</p>
                                </div>
                                <button class="apply-recommendation-btn text-xs font-semibold py-1 px-3 rounded border border-green-300 text-green-700 hover:bg-green-50" data-rec-id="${rec.id}">Apply</button>
                            </div>
                        </div>
                    </div>`;
            }).join('')
            : '<div class="p-10 text-center text-gray-500 border rounded-lg bg-gray-50">All caught up! No obvious inconsistencies detected right now.</div>';

        const wrapper = document.getElementById('interactive-table-wrapper');
        if (wrapper) {
            wrapper.innerHTML = `<div class="space-y-4">${recommendationCards}</div>`;
        }

        updateSmartRecommendationSelectionCount();
    }

    function renderPimSkuMappingView() {
        // Check if PIM analysis results exist
        const pimResults = window.pimAnalysisResults;
        
        if (!pimResults || !pimResults.category_facet_counts || pimResults.category_facet_counts.length === 0) {
            ui.resultsContainer.innerHTML = createReportContainer(
                'PIM SKU Mapping',
                'No PIM analysis results available.',
                '',
                'Please upload your PIM product data from the Taxonomy & Architecture Analysis lens view first. The PIM upload interface is located at the top of the lens selection page.'
            );
            return;
        }

        tableState.activeLens = 'pim-sku-mapping';
        
        const subtitle = 'Detailed SKU mapping results showing which SKUs match each category-facet combination.';
        const customContent = `
            <div class="p-3 bg-blue-50 border border-blue-200 rounded-lg text-sm text-gray-700">
                <strong>PIM Data Loaded:</strong> ${pimResults.total_skus} total SKUs, ${pimResults.matched_skus} matched (${Math.round(pimResults.matched_skus / pimResults.total_skus * 100)}%)
            </div>`;
        const explainer = `
            <div class="text-sm text-gray-600 bg-blue-50 border border-blue-200 p-3 rounded-md mb-4">
                <b>SKU Mapping Results:</b> This table shows all category-facet combinations from the Category Overhaul Matrix and which SKUs from your PIM data match each combination.
                <ul class="list-disc list-inside mt-2">
                    <li>Each row represents a unique category-facet combination.</li>
                    <li>The <b>SKU Count</b> column shows how many SKUs match this combination.</li>
                    <li>The <b>SKU IDs</b> column lists all matching SKU IDs for this combination.</li>
                    <li>This data is used to highlight gaps in the Category Overhaul Matrix and Category Consolidation exports.</li>
                </ul>
            </div>`;

        ui.resultsContainer.innerHTML = createReportContainer('PIM SKU Mapping', subtitle, customContent, explainer);
        
        // Display results
        displayPimAnalysisResults(pimResults);
    }

    function displayPimAnalysisResults(result) {
        const { category_facet_counts, total_skus, matched_skus, sku_ids_by_combination } = result;
        
        // Store PIM analysis results globally for use in exports
        window.pimAnalysisResults = result;
        
        const statusDiv = document.getElementById('pim-analysis-status');
        if (statusDiv) {
            statusDiv.className = 'p-4 bg-green-50 border border-green-200 rounded-lg text-green-700';
            statusDiv.innerHTML = `
                <div class="font-semibold">Analysis Complete!</div>
                <div class="text-sm mt-1">Total SKUs: ${total_skus} | Matched SKUs: ${matched_skus} (${Math.round(matched_skus / total_skus * 100)}%)</div>
            `;
        }
        
        // Validate and format data with SKU IDs as a display string
        if (!category_facet_counts || !Array.isArray(category_facet_counts)) {
            console.error('Invalid category_facet_counts:', category_facet_counts, 'Full result:', result);
            const tableWrapper = document.getElementById('interactive-table-wrapper');
            if (tableWrapper) {
                tableWrapper.innerHTML = '<div class="p-8 text-center text-gray-500 border rounded-lg bg-gray-50">No category-facet data available. Please check your PIM file format.</div>';
            }
            return;
        }
        
        const formattedData = category_facet_counts.map((row, index) => {
            // Handle both 'SKU IDs' (with space) and 'SKU_IDs' (underscore) formats
            let skuIds = row['SKU IDs'] || row.SKU_IDs || row['SKU_IDs'] || [];
            
            // Debug: log first few rows to see structure
            if (index < 3) {
                console.log(`Row ${index} structure:`, {
                    'Category Mapping': row['Category Mapping'],
                    'Facet Attribute': row['Facet Attribute'],
                    'Facet Value': row['Facet Value'],
                    'SKU Count': row['SKU Count'],
                    'SKU IDs raw': skuIds,
                    'SKU IDs type': typeof skuIds,
                    'Is array': Array.isArray(skuIds)
                });
            }
            
            // Ensure it's an array
            let skuIdsArray = [];
            if (Array.isArray(skuIds)) {
                // Filter out null, empty, or 'nan' values
                skuIdsArray = skuIds.filter(id => {
                    if (id == null || id === '') return false;
                    const idStr = String(id).trim();
                    return idStr && idStr.toLowerCase() !== 'nan' && idStr !== 'undefined';
                });
            } else if (skuIds) {
                // If it's a string with commas, split it
                if (typeof skuIds === 'string') {
                    skuIdsArray = skuIds.split(',').map(id => id.trim()).filter(id => id && id.toLowerCase() !== 'nan');
                } else {
                    skuIdsArray = [String(skuIds).trim()];
                }
            }
            
            const skuIdsString = skuIdsArray.length > 0 ? skuIdsArray.join(', ') : '(None)';
            
            return {
                'Category Mapping': row['Category Mapping'],
                'Facet Attribute': row['Facet Attribute'] || '',
                'Facet Value': row['Facet Value'],
                'SKU Count': row['SKU Count'] || 0,
                'SKU IDs': skuIdsString,
                '_SKU_IDS_ARRAY': skuIdsArray  // Keep original array for internal use
            };
        });
        
        // Display results in table
        const tableWrapper = document.getElementById('interactive-table-wrapper');
        if (tableWrapper && formattedData.length > 0) {
            const headers = ['Category Mapping', 'Facet Attribute', 'Facet Value', 'SKU Count', 'SKU IDs'];
            const defaultSortKey = 'SKU Count';
            
            tableState.activeLens = 'pim-sku-mapping';
            initializeTable(formattedData, headers, defaultSortKey, 'Category Mapping');
        } else if (tableWrapper) {
            tableWrapper.innerHTML = '<div class="p-8 text-center text-gray-500 border rounded-lg bg-gray-50">No matches found. Check your PIM data format and try again.</div>';
        }
    }

    function initializeTable(data, headers, defaultSortKey, defaultSearchKey, competitorDomains = []) {
        tableState.fullData = data;
        if (Array.isArray(tableState.fullData)) {
            tableState.fullData.forEach((row, idx) => {
                if (!row || typeof row !== 'object') return;
                if (Object.prototype.hasOwnProperty.call(row, '__rowId')) {
                    row.__rowId = idx;
                } else {
                    Object.defineProperty(row, '__rowId', { value: idx, enumerable: false, writable: true });
                }
            });
        }
        tableState.headers = headers;
        tableState.sortKey = defaultSortKey;
        tableState.sortDir = 'desc';
        tableState.searchTerm = '';
        tableState.searchKey = defaultSearchKey;
        tableState.currentPage = 1;
        tableState.rowsPerPage = 25;
        tableState.competitorDomainHeaders = competitorDomains;
        tableState.hideZeroTraffic = false;

        renderTableAndControls();
    }

    function renderTableAndControls() {
        const tableWrapper = document.getElementById('interactive-table-wrapper');
        const paginationWrapper = document.getElementById('pagination-controls-wrapper');
        if (!tableWrapper || !paginationWrapper) return;

        let viewData = getFilteredData();
        
        const searchInput = document.getElementById('table-search-input');
        if (tableState.searchTerm && tableState.searchKey) {
            try {
                new RegExp(tableState.searchTerm, 'i');
                if (searchInput) searchInput.style.borderColor = '';
            } catch (e) {
                if (searchInput) searchInput.style.borderColor = 'red';
            }
        } else {
            if (searchInput) searchInput.style.borderColor = '';
        }

        const filteredRowCount = viewData.length;
        const start = (tableState.currentPage - 1) * tableState.rowsPerPage;
        const end = start + tableState.rowsPerPage;
        const paginatedData = viewData.slice(start, end);

        tableState.headers = tableState.headers.filter(h => h !== 'KeywordDetails' && h !== 'FacetValueDetails');
        tableWrapper.innerHTML = createTableFromArray(paginatedData, tableState.headers, viewData);
        paginationWrapper.innerHTML = createPaginationControls(filteredRowCount);
    }
    
    function setupEventListeners() {
        ui.resultsContainer.addEventListener('click', handleResultsNavigation);
        ui.modalCloseBtn.addEventListener('click', closeKeywordModal);
        ui.keywordModal.addEventListener('click', (e) => { if(e.target === ui.keywordModal) closeKeywordModal(); });
        let searchTimeout;
        ui.resultsContainer.addEventListener('input', e => {
            const target = e.target;
            if (target.id === 'table-search-input') {
                clearTimeout(searchTimeout);
                searchTimeout = setTimeout(() => {
                    tableState.searchTerm = target.value;
                    tableState.currentPage = 1;
                    renderTableAndControls();
                }, 300);
            } else if (target.id === 'rows-per-page-select') {
                tableState.rowsPerPage = parseInt(target.value, 10);
                tableState.currentPage = 1;
                renderTableAndControls();
            } else if (target.classList.contains('smart-rec-select')) {
                const recId = target.dataset.recId;
                if (!recId) return;
                if (target.checked) {
                    smartRecommendationSelections.add(recId);
                } else {
                    smartRecommendationSelections.delete(recId);
                }
                updateSmartRecommendationSelectionCount();
            }
        });

        ui.resultsContainer.addEventListener('change', e => {
            const target = e.target;
            if (target.id === 'row-edit-column') {
                updateRowEditorValueOptions(target.value);
            } else if (target.id === 'row-edit-action') {
                updateRowEditorActionVisibility(target.value);
            }
        });

        ui.resultsContainer.addEventListener('submit', e => {
            if (e.target && e.target.id === 'row-edit-form') {
                e.preventDefault();
                handleRowEditFormSubmit(e.target);
            }
        });
        
        const ourFileInput = document.getElementById('our-file');
        const compFileInput = document.getElementById('competitor-files');
        const onsiteFileInput = document.getElementById('onsite-file');
        const analyseBtn = document.getElementById('analyse-btn');
        const columnMappingContainer = document.getElementById('column-mapping-container');
        
        ourFileInput.addEventListener('change', async () => {
            updateFileLabel(ourFileInput);
            if (ourFileInput.files.length > 0) {
                const file = ourFileInput.files[0];
                const text = await file.text();
                
                // Debug: Log the first few characters to understand the format
                console.log('CSV first line:', text.split('\n')[0]);
                console.log('CSV first 200 chars:', text.substring(0, 200));
                
                // Parse CSV headers properly, handling quoted fields and different delimiters
                function parseCSVHeaders(csvText) {
                    const firstLine = csvText.split('\n')[0];
                    
                    // First, try to detect the delimiter
                    const commaCount = (firstLine.match(/,/g) || []).length;
                    const tabCount = (firstLine.match(/\t/g) || []).length;
                    const semicolonCount = (firstLine.match(/;/g) || []).length;
                    
                    let delimiter = ',';
                    if (tabCount > commaCount && tabCount > semicolonCount) {
                        delimiter = '\t';
                    } else if (semicolonCount > commaCount) {
                        delimiter = ';';
                    }
                    
                    const headers = [];
                    let current = '';
                    let inQuotes = false;
                    
                    for (let i = 0; i < firstLine.length; i++) {
                        const char = firstLine[i];
                        
                        if (char === '"') {
                            inQuotes = !inQuotes;
                        } else if (char === delimiter && !inQuotes) {
                            headers.push(current.trim().replace(/^"|"$/g, ''));
                            current = '';
                        } else {
                            current += char;
                        }
                    }
                    
                    // Add the last field
                    headers.push(current.trim().replace(/^"|"$/g, ''));
                    
                    // If we only got one header, try splitting by spaces as fallback
                    if (headers.length === 1 && headers[0].includes(' ')) {
                        console.log('Falling back to space-based splitting for:', headers[0]);
                        // Split by spaces but be more careful about quoted strings
                        const spaceSplit = headers[0].split(/\s+/).map(h => h.trim().replace(/^"|"$/g, ''));
                        console.log('Space-split result:', spaceSplit);
                        return spaceSplit;
                    }
                    
                    console.log('Parsed headers:', headers);
                    return headers;
                }
                
                const headers = parseCSVHeaders(text);

                const COLS_TO_EXCLUDE_FROM_UI = [
                    'country code', 'location', 'serp features', 'kd', 'cpc', 'paid traffic',
                    'current url inside', 'updated', 'branded', 'local', 'navigational',
                    'informational', 'commercial', 'transactional'
                ];
                // Also exclude the normalized versions (without spaces) to match backend
                const COLS_TO_EXCLUDE_NORMALIZED = [
                    'countrycode', 'location', 'serpfeatures', 'kd', 'cpc', 'paidtraffic',
                    'currenturlinside', 'updated', 'branded', 'local', 'navigational',
                    'informational', 'commercial', 'transactional'
                ];
                console.log('All headers before filtering:', headers);
                const filteredHeaders = headers.filter(h => 
                    !COLS_TO_EXCLUDE_FROM_UI.includes(h.toLowerCase()) && 
                    !COLS_TO_EXCLUDE_NORMALIZED.includes(h.toLowerCase().replace(/\s+/g, ''))
                );
                console.log('Headers after filtering:', filteredHeaders);
                console.log('Excluded headers:', headers.filter(h => 
                    COLS_TO_EXCLUDE_FROM_UI.includes(h.toLowerCase()) || 
                    COLS_TO_EXCLUDE_NORMALIZED.includes(h.toLowerCase().replace(/\s+/g, ''))
                ));
                
                // If filtering removed all headers, use the original headers
                const finalHeaders = filteredHeaders.length > 0 ? filteredHeaders : headers;
                console.log('Final headers to use:', finalHeaders);
                populateColumnMappers(finalHeaders);
                columnMappingContainer.classList.remove('hidden');
            } else {
                columnMappingContainer.classList.add('hidden');
                document.getElementById('column-mappers').innerHTML = '';
            }
            checkCanAnalyse();
        });
        
        compFileInput.addEventListener('change', () => { updateFileLabel(compFileInput); checkCanAnalyse(); });
        onsiteFileInput.addEventListener('change', () => updateFileLabel(onsiteFileInput));
        analyseBtn.addEventListener('click', handleAnalysis);
    }
    
    document.addEventListener('DOMContentLoaded', () => {
        renderInitialControlsView();
        initializeProjectManager();
    });

    // Project Management System
    let currentProject = null;
    let projectManager = {
        modal: document.getElementById('project-manager-modal'),
        newProjectModal: document.getElementById('new-project-modal'),
        editProjectModal: document.getElementById('edit-project-modal'),
        projectList: document.getElementById('project-list'),
        newProjectForm: document.getElementById('new-project-form'),
        editProjectForm: document.getElementById('edit-project-form')
    };

    function initializeProjectManager() {
        // Project manager button
        document.getElementById('project-manager-btn').addEventListener('click', () => {
            projectManager.modal.classList.remove('hidden');
            loadProjects();
        });

        // Close buttons
        document.getElementById('project-modal-close-btn').addEventListener('click', () => {
            projectManager.modal.classList.add('hidden');
        });

        document.getElementById('new-project-modal-close-btn').addEventListener('click', () => {
            projectManager.newProjectModal.classList.add('hidden');
        });

        document.getElementById('cancel-new-project-btn').addEventListener('click', () => {
            projectManager.newProjectModal.classList.add('hidden');
        });

        // New project button
        document.getElementById('new-project-btn').addEventListener('click', () => {
            projectManager.newProjectModal.classList.remove('hidden');
        });

        // New project form
        projectManager.newProjectForm.addEventListener('submit', handleCreateProject);

        // Edit project form
        projectManager.editProjectForm.addEventListener('submit', handleEditProject);

        // Edit project modal close buttons
        document.getElementById('edit-project-modal-close-btn').addEventListener('click', () => {
            projectManager.editProjectModal.classList.add('hidden');
        });

        document.getElementById('cancel-edit-project-btn').addEventListener('click', () => {
            projectManager.editProjectModal.classList.add('hidden');
        });

        // Close modals when clicking outside
        projectManager.modal.addEventListener('click', (e) => {
            if (e.target === projectManager.modal) {
                projectManager.modal.classList.add('hidden');
            }
        });

        projectManager.newProjectModal.addEventListener('click', (e) => {
            if (e.target === projectManager.newProjectModal) {
                projectManager.newProjectModal.classList.add('hidden');
            }
        });

        projectManager.editProjectModal.addEventListener('click', (e) => {
            if (e.target === projectManager.editProjectModal) {
                projectManager.editProjectModal.classList.add('hidden');
            }
        });
    }

    async function loadProjects() {
        try {
            const response = await fetch('/api/projects?analysis_type=taxonomy_architecture', {
                headers: {
                    'X-API-KEY': API_KEY
                }
            });

            if (!response.ok) {
                throw new Error('Failed to load projects');
            }

            const projects = await response.json();
            renderProjectList(projects);
        } catch (error) {
            console.error('Error loading projects:', error);
            showNotification('Error loading projects', 'error');
        }
    }

    function renderProjectList(projects) {
        if (projects.length === 0) {
            projectManager.projectList.innerHTML = `
                <div class="text-center py-8 text-gray-500">
                    <p>No projects found. Create your first project to get started!</p>
                </div>
            `;
            return;
        }

        projectManager.projectList.innerHTML = projects.map(project => `
            <div class="border rounded-lg p-4 hover:bg-gray-50 transition-colors">
                <div class="flex justify-between items-start mb-2">
                    <div>
                        <h4 class="font-semibold text-lg">${project.name}</h4>
                        <p class="text-sm text-gray-600">${project.description || 'No description'}</p>
                    </div>
                    <div class="flex gap-2">
                        <button onclick="editProject(${project.id}, '${project.name.replace(/'/g, "\\'")}', '${(project.description || '').replace(/'/g, "\\'")}')" 
                                class="bg-yellow-600 hover:bg-yellow-700 text-white px-3 py-1 rounded text-sm transition-colors">
                            Edit
                        </button>
                        <button onclick="loadProject(${project.id})" 
                                class="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded text-sm transition-colors">
                            Load
                        </button>
                        <button onclick="deleteProject(${project.id})" 
                                class="bg-red-600 hover:bg-red-700 text-white px-3 py-1 rounded text-sm transition-colors">
                            Delete
                        </button>
                    </div>
                </div>
                <div class="text-xs text-gray-500">
                    Created: ${new Date(project.created_at).toLocaleDateString()}
                    ${project.updated_at !== project.created_at ? 
                        ` | Updated: ${new Date(project.updated_at).toLocaleDateString()}` : ''}
                </div>
            </div>
        `).join('');
    }

    async function handleCreateProject(e) {
        e.preventDefault();
        
        const formData = new FormData(e.target);
        const projectData = {
            name: formData.get('name'),
            description: formData.get('description'),
            analysis_type: 'taxonomy_architecture'
        };

        try {
            const response = await fetch('/api/projects', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-KEY': API_KEY
                },
                body: JSON.stringify(projectData)
            });

            if (!response.ok) {
                throw new Error('Failed to create project');
            }

            const project = await response.json();
            currentProject = project;
            
            projectManager.newProjectModal.classList.add('hidden');
            projectManager.newProjectForm.reset();
            
            showNotification('Project created successfully!', 'success');
            loadProjects();
            
            // Update UI to show current project
            updateProjectUI();
        } catch (error) {
            console.error('Error creating project:', error);
            showNotification('Error creating project', 'error');
        }
    }

    function editProject(projectId, currentName, currentDescription) {
        // Populate the edit form with current values
        document.getElementById('edit-project-id').value = projectId;
        document.getElementById('edit-project-name').value = currentName;
        document.getElementById('edit-project-description').value = currentDescription;
        
        // Show the edit modal
        projectManager.editProjectModal.classList.remove('hidden');
    }

    async function handleEditProject(e) {
        e.preventDefault();
        
        const formData = new FormData(e.target);
        const projectId = formData.get('id');
        const projectData = {
            name: formData.get('name'),
            description: formData.get('description')
        };

        try {
            const response = await fetch(`/api/projects/${projectId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-KEY': API_KEY
                },
                body: JSON.stringify(projectData)
            });

            if (!response.ok) {
                throw new Error('Failed to update project');
            }

            projectManager.editProjectModal.classList.add('hidden');
            projectManager.editProjectForm.reset();
            
            showNotification('Project updated successfully!', 'success');
            loadProjects();
            
            // Update UI if this is the current project
            if (currentProject && currentProject.id == projectId) {
                currentProject.name = projectData.name;
                currentProject.description = projectData.description;
                updateProjectUI();
            }
        } catch (error) {
            console.error('Error updating project:', error);
            showNotification('Error updating project', 'error');
        }
    }

    async function loadProject(projectId) {
        try {
            const response = await fetch(`/api/projects/${projectId}/load`, {
                headers: {
                    'X-API-KEY': API_KEY
                }
            });

            if (!response.ok) {
                throw new Error('Failed to load project');
            }

            const projectData = await response.json();
            currentProject = projectData.project;
            
            // Debug logging
            console.log('Project data loaded:', projectData);
            console.log('Project state available:', !!projectData.state);
            if (projectData.state) {
                console.log('State keys:', Object.keys(projectData.state));
                console.log('Analysis results available:', !!projectData.state.analysisResults);
                if (projectData.state.analysisResults) {
                    console.log('Analysis results keys:', Object.keys(projectData.state.analysisResults));
                }
            }
            
            // Store file metadata for restoration
            if (projectData.file_metadata) {
                window.projectFileMetadata = projectData.file_metadata;
            } else {
                // Build file metadata from files if not provided
                window.projectFileMetadata = {};
                if (projectData.files && projectData.files.pim_file) {
                    window.projectFileMetadata.pim_file = {
                        path: projectData.files.pim_file,
                        original_name: projectData.files.pim_file_original_name || 'pim_data.csv'
                    };
                }
            }
            
            // Load project state if available
            if (projectData.state) {
                loadProjectState(projectData.state);
            } else {
                // If no state, just show initial controls
                renderInitialControlsView();
                showNotification('Project loaded (no analysis results found)', 'info');
            }
            
            projectManager.modal.classList.add('hidden');
            
            // Update UI to show current project
            updateProjectUI();
        } catch (error) {
            console.error('Error loading project:', error);
            showNotification('Error loading project', 'error');
        }
    }

    function loadProjectState(state) {
        // Load analysis options if available
        if (state.analysisOptions) {
            restoreAnalysisOptions(state.analysisOptions);
        }
        
        // Load table state if available
        if (state.tableState) {
            tableState = { ...tableState, ...state.tableState };
        }
        
        // Load override rules if available
        if (state.overrideRules) {
            overrideRules = state.overrideRules;
        }
        
        // Load PIM analysis results if available
        if (state.pimAnalysisResults) {
            window.pimAnalysisResults = state.pimAnalysisResults;
            console.log('Loaded PIM analysis results:', state.pimAnalysisResults);
        }
        if (state.contentGapSkuCounts) {
            contentGapSkuCounts = state.contentGapSkuCounts;
            window.contentGapSkuCounts = state.contentGapSkuCounts;
        }
        if (state.contentGapTopicSkuIds) {
            contentGapTopicSkuIds = state.contentGapTopicSkuIds;
            window.contentGapTopicSkuIds = state.contentGapTopicSkuIds;
        }
        if (state.contentGapGroupSkuIds) {
            contentGapGroupSkuIds = state.contentGapGroupSkuIds;
            window.contentGapGroupSkuIds = state.contentGapGroupSkuIds;
        }
        if (state.contentGapTopicSkuIdKeywordMap) {
            contentGapTopicSkuIdKeywordMap = state.contentGapTopicSkuIdKeywordMap;
            window.contentGapTopicSkuIdKeywordMap = state.contentGapTopicSkuIdKeywordMap;
        }
        if (state.contentGapGroupSkuIdKeywordMap) {
            contentGapGroupSkuIdKeywordMap = state.contentGapGroupSkuIdKeywordMap;
            window.contentGapGroupSkuIdKeywordMap = state.contentGapGroupSkuIdKeywordMap;
        }
        
        // Load analysis results if available
        if (state.analysisResults && Object.keys(state.analysisResults).length > 0) {
            analysisResults = state.analysisResults;
            
            // Debug logging
            console.log('Loaded analysis results:', Object.keys(analysisResults));
            console.log('Analysis results content:', analysisResults);
            
            // Check if we have any meaningful analysis data
            const hasValidData = hasValidAnalysisData(analysisResults);
            
            if (hasValidData) {
                // Jump directly to the results view
                ui.controlsContainer.classList.add('hidden');
                ui.progressContainer.classList.add('hidden');
                ui.resultsContainer.classList.remove('hidden');
                
                // Render the lens selection view with the loaded results
                renderLensSelectionView();
                
                showNotification('Analysis results restored from project!', 'success');
            } else {
                // If no valid analysis data, show initial controls but indicate files are available
                renderInitialControlsView();
                showNotification('Project loaded - files available for analysis', 'info');
            }
        } else {
            // If no analysis results, show initial controls but indicate files are available
            renderInitialControlsView();
            showNotification('Project loaded - files available for analysis', 'info');
        }
    }

    function hasValidAnalysisData(analysisResults) {
        console.log('Checking for valid analysis data in:', analysisResults);
        
        // Check for various types of analysis data
        const dataTypes = [
            'categoryOverhaulMatrixReport',
            'facetPotentialReport',
            'keywordGapReport',
            'topicGapReport',
            'keywordThreatsReport',
            'topicThreatsReport',
            'keywordMarketShareReport',
            'groupMarketShareReport'
        ];
        
        for (const dataType of dataTypes) {
            if (analysisResults[dataType] && Array.isArray(analysisResults[dataType]) && analysisResults[dataType].length > 0) {
                console.log(`Found valid data in ${dataType}:`, analysisResults[dataType].length, 'items');
                return true;
            }
        }
        
        // Also check if we have any non-empty arrays in the results
        for (const key in analysisResults) {
            if (Array.isArray(analysisResults[key]) && analysisResults[key].length > 0) {
                console.log(`Found valid data in ${key}:`, analysisResults[key].length, 'items');
                return true;
            }
        }
        
        console.log('No valid analysis data found');
        return false;
    }

    function restoreAnalysisOptions(options) {
        // Restore analysis checkboxes
        if (options.lensesToRun) {
            const checkboxes = {
                'run_content_gaps': options.lensesToRun.content_gaps,
                'run_competitive_opportunities': options.lensesToRun.competitive_opportunities,
                'run_market_share': options.lensesToRun.market_share,
                'run_taxonomy_analysis': options.lensesToRun.taxonomy_analysis
            };
            
            Object.entries(checkboxes).forEach(([id, checked]) => {
                const element = document.getElementById(id);
                if (element) element.checked = checked;
            });
        }
        
        // Restore rank filters
        if (options.rankFrom) {
            const rankFromEl = document.getElementById('rank-from');
            if (rankFromEl) rankFromEl.value = options.rankFrom;
        }
        
        if (options.rankTo) {
            const rankToEl = document.getElementById('rank-to');
            if (rankToEl) rankToEl.value = options.rankTo;
        }
        
        // Restore onsite date range
        if (options.onsiteDateRange) {
            const onsiteDateEl = document.getElementById('onsite-date-range');
            if (onsiteDateEl) onsiteDateEl.value = options.onsiteDateRange;
        }
        
        // Restore branded exclusions
        if (options.brandedExclusions) {
            const exclusionsEl = document.getElementById('branded-exclusions');
            if (exclusionsEl) exclusionsEl.value = options.brandedExclusions;
        }
        
        // Restore column mappings (this will be handled when files are loaded)
        if (options.columnMap) {
            // Store column mappings to be applied when files are loaded
            window.restoredColumnMap = options.columnMap;
        }
    }

    async function saveProjectState() {
        if (!currentProject) {
            showNotification('No active project to save', 'error');
            return;
        }

        // Debug logging
        console.log('Saving project state...');
        console.log('Current analysisResults:', analysisResults);
        console.log('Current tableState:', tableState);
        console.log('Current overrideRules:', overrideRules);

        // Capture current analysis options and settings
        const analysisOptions = {
            columnMap: {},
            excludedKeywords: [],
            lensesToRun: {
                content_gaps: document.getElementById('run_content_gaps')?.checked || false,
                competitive_opportunities: document.getElementById('run_competitive_opportunities')?.checked || false,
                market_share: document.getElementById('run_market_share')?.checked || false,
                taxonomy_analysis: document.getElementById('run_taxonomy_analysis')?.checked || false,
            },
            rankFrom: document.getElementById('rank-from')?.value || '',
            rankTo: document.getElementById('rank-to')?.value || '',
            onsiteDateRange: document.getElementById('onsite-date-range')?.value || '',
            brandedExclusions: document.getElementById('branded-exclusions')?.value || ''
        };

        // Capture column mappings if they exist
        document.querySelectorAll('#column-mappers select').forEach(s => { 
            if(s.value) analysisOptions.columnMap[s.id] = s.value; 
        });

        // Capture excluded keywords
        const excludedKeywordsRaw = document.getElementById('branded-exclusions')?.value || '';
        analysisOptions.excludedKeywords = excludedKeywordsRaw.split('\n').map(kw => kw.trim()).filter(kw => kw);

        const stateData = {
            analysisResults: analysisResults,
            tableState: tableState,
            overrideRules: overrideRules,
            analysisOptions: analysisOptions,
            pimAnalysisResults: window.pimAnalysisResults || null,  // Save PIM analysis results
            contentGapSkuCounts: window.contentGapSkuCounts || contentGapSkuCounts || null,
            contentGapTopicSkuIds: window.contentGapTopicSkuIds || contentGapTopicSkuIds || null,
            contentGapGroupSkuIds: window.contentGapGroupSkuIds || contentGapGroupSkuIds || null,
            contentGapTopicSkuIdKeywordMap: window.contentGapTopicSkuIdKeywordMap || contentGapTopicSkuIdKeywordMap || null,
            contentGapGroupSkuIdKeywordMap: window.contentGapGroupSkuIdKeywordMap || contentGapGroupSkuIdKeywordMap || null,
            savedAt: new Date().toISOString()
        };

        console.log('State data to save:', stateData);

        try {
            const response = await fetch(`/api/projects/${currentProject.id}/save`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-KEY': API_KEY
                },
                body: JSON.stringify(stateData)
            });

            if (!response.ok) {
                throw new Error('Failed to save project state');
            }

            showNotification('Project saved successfully!', 'success');
        } catch (error) {
            console.error('Error saving project:', error);
            showNotification('Error saving project', 'error');
        }
    }

    async function deleteProject(projectId) {
        if (!confirm('Are you sure you want to delete this project? This action cannot be undone.')) {
            return;
        }

        try {
            const response = await fetch(`/api/projects/${projectId}`, {
                method: 'DELETE',
                headers: {
                    'X-API-KEY': API_KEY
                }
            });

            if (!response.ok) {
                throw new Error('Failed to delete project');
            }

            showNotification('Project deleted successfully!', 'success');
            loadProjects();
            
            // If this was the current project, clear it
            if (currentProject && currentProject.id === projectId) {
                currentProject = null;
                updateProjectUI();
            }
        } catch (error) {
            console.error('Error deleting project:', error);
            showNotification('Error deleting project', 'error');
        }
    }

    function updateProjectUI() {
        const projectBtn = document.getElementById('project-manager-btn');
        
        if (currentProject) {
            projectBtn.textContent = `Project: ${currentProject.name}`;
            projectBtn.classList.add('bg-green-600', 'hover:bg-green-700');
            projectBtn.classList.remove('bg-blue-700', 'hover:bg-blue-600');
        } else {
            projectBtn.textContent = 'Project Manager';
            projectBtn.classList.remove('bg-green-600', 'hover:bg-green-700');
            projectBtn.classList.add('bg-blue-700', 'hover:bg-blue-600');
        }
    }

    function showNotification(message, type = 'info') {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `fixed top-4 right-4 p-4 rounded-lg shadow-lg z-50 ${
            type === 'success' ? 'bg-green-500 text-white' :
            type === 'error' ? 'bg-red-500 text-white' :
            'bg-blue-500 text-white'
        }`;
        notification.textContent = message;
        
        document.body.appendChild(notification);
        
        // Remove after 3 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 3000);
    }

    // Make functions globally available
    window.loadProject = loadProject;
    window.deleteProject = deleteProject;
    window.editProject = editProject;
    window.saveProjectState = saveProjectState;
    window.restoreProjectFiles = restoreProjectFiles;

    function restoreProjectFiles() {
        if (!window.projectFileMetadata) {
            showNotification('No project files to restore', 'error');
            return;
        }

        // Update file input labels to show restored files
        const metadata = window.projectFileMetadata;
        
        if (metadata.our_file) {
            const ourFileLabel = document.querySelector('label[for="our-file"]');
            if (ourFileLabel) {
                ourFileLabel.innerHTML = `<span class="text-green-600">✅ ${metadata.our_file.original_name}</span>`;
            }
        }
        
        if (metadata.competitor_files && metadata.competitor_files.length > 0) {
            const compFileLabel = document.querySelector('label[for="competitor-files"]');
            if (compFileLabel) {
                const fileNames = metadata.competitor_files.map(f => f.original_name).join(', ');
                compFileLabel.innerHTML = `<span class="text-green-600">✅ ${fileNames}</span>`;
            }
        }
        
        if (metadata.onsite_file) {
            const onsiteFileLabel = document.querySelector('label[for="onsite-file"]');
            if (onsiteFileLabel) {
                onsiteFileLabel.innerHTML = `<span class="text-green-600">✅ ${metadata.onsite_file.original_name}</span>`;
            }
        }

        // Apply restored column mappings if available
        if (window.restoredColumnMap) {
            Object.entries(window.restoredColumnMap).forEach(([elementId, value]) => {
                const element = document.getElementById(elementId);
                if (element) {
                    element.value = value;
                }
            });
        }

        showNotification('Project files restored successfully!', 'success');
        
        // Enable the analyze button since we have files
        const analyzeBtn = document.getElementById('analyse-btn');
        if (analyzeBtn) {
            analyzeBtn.disabled = false;
        }
    }

})();