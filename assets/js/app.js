(function() {
    'use strict';
    
    let analysisResults = {};
    let pollingInterval = null;
    let tableState = {
        fullData: [], headers: [], sortKey: null, sortDir: 'desc',
        searchTerm: '', searchKey: null, currentPage: 1, rowsPerPage: 25,
        timeframe: 'monthly',
        hideEntities: false,
        hideFeatures: false
    };
    let overrideRules = [];
    let inProductNameFacets = new Set(); // To store state of "In Product Name" checkboxes
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

            bodyHtml += `<tr class="hover:bg-gray-50">${cells}</tr>`;

            if (isNestableReport) {
                let nestedHtml = '';
                if (row.KeywordDetails) {
                    nestedHtml = createNestedKeywordTable(row.KeywordDetails);
                } else if (row.FacetValueDetails) {
                    nestedHtml = createNestedFacetValueTable(row.FacetValueDetails);
                }
                bodyHtml += `<tr class="keyword-details-row"><td colspan="${headers.length + (isNestableReport ? 1 : 0) + (isFacetPotentialReport ? 1 : 0)}" class="keyword-details-cell">${nestedHtml}</td></tr>`;
            }
        });
        
        let footerHtml = '';
        if (fullFilteredData && fullFilteredData.length > 0) {
            const totalRowData = calculateTotalRow(headers, fullFilteredData);
            let footerCells = '';
            if(isNestableReport) footerCells += '<td></td>';
            footerCells += headers.map(h => `<td class="p-3 text-sm">${totalRowData[h]}</td>`).join('');
            if(isFacetPotentialReport) footerCells += '<td></td>';
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

    function exportCategoryOverhaulToExcel(data, headers, fileName) {
        const wb = XLSX.utils.book_new();

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
        const ws1 = XLSX.utils.json_to_sheet(topLevelData, { header: [...topLevelHeaders, 'Category & Facet Key'] });
        XLSX.utils.book_append_sheet(wb, ws1, "Category Matrix");

        const keywordBreakdownData = [];
        const annualSuffix = tableState.timeframe === 'annual' ? 'Annual' : 'Monthly';
        
        data.forEach(parentRow => {
            const rowKey = createRowKey(parentRow, keyGenHeaders);
            if (parentRow.KeywordDetails && parentRow.KeywordDetails.length > 0) {
                // Debug: Log the first keyword detail to see its structure
                if (keywordBreakdownData.length === 0) {
                    console.log('Sample KeywordDetail structure:', parentRow.KeywordDetails[0]);
                    console.log('Sample Keyword value:', parentRow.KeywordDetails[0]['Keyword']);
                }
                parentRow.KeywordDetails.forEach(keywordRow => {
                    const newBreakdownRow = {};
                    keyGenHeaders.forEach(pHeader => {
                        newBreakdownRow[pHeader] = parentRow[pHeader];
                    });
                    // Use the static field names that Python creates
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

        console.log('Created keywordBreakdownData with', keywordBreakdownData.length, 'rows');
        if (keywordBreakdownData.length > 0) {
            console.log('Sample breakdown row structure:', Object.keys(keywordBreakdownData[0]));
            console.log('Sample breakdown row Keyword value:', keywordBreakdownData[0]['Keyword']);
        }
        if (keywordBreakdownData.length > 0) {
            console.log('Creating Excel sheet for Keyword Breakdown...');
            
            // Reorder columns to put Keyword in Column B
            const reorderedData = keywordBreakdownData.map(row => {
                const reorderedRow = {};
                // First column: Category & Facet Key
                reorderedRow['Category & Facet Key'] = row['Category & Facet Key'];
                // Second column: Keyword
                reorderedRow['Keyword'] = row['Keyword'];
                // Add all other columns in their original order
                Object.keys(row).forEach(key => {
                    if (key !== 'Category & Facet Key' && key !== 'Keyword') {
                        reorderedRow[key] = row[key];
                    }
                });
                return reorderedRow;
            });
            
            const ws2 = XLSX.utils.json_to_sheet(reorderedData);
            
            // Set column widths to ensure all columns are visible
            const colWidths = [];
            const headers = Object.keys(reorderedData[0] || {});
            headers.forEach(header => {
                // Set reasonable column widths based on content
                if (header === 'Keyword') {
                    colWidths.push({ wch: 30 }); // Wider for keywords
                } else if (header === 'URL') {
                    colWidths.push({ wch: 50 }); // Wider for URLs
                } else if (header === 'Category & Facet Key') {
                    colWidths.push({ wch: 25 }); // Wider for category keys
                } else if (header.includes('Traffic') || header.includes('Searches')) {
                    colWidths.push({ wch: 15 }); // Medium for numbers
                } else {
                    colWidths.push({ wch: 12 }); // Default width
                }
            });
            ws2['!cols'] = colWidths;
            
            console.log('Excel sheet created, appending to workbook...');
            XLSX.utils.book_append_sheet(wb, ws2, "Keyword Breakdown");
            console.log('Sheet appended successfully');
        } else {
            console.log('No keyword breakdown data to export');
        }

        XLSX.writeFile(wb, `${fileName}.xlsx`);
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
                                    <div class="flex justify-between items-center mb-2"><h4 class="font-semibold">Active Rules</h4>${overrideRules.length > 0 ? '<button id="clear-all-rules-btn" class="text-xs text-red-600 hover:underline">Clear All Rules</button>' : ''}</div>
                                    <ul id="active-rules-list" class="bg-white rounded-md border">${overrideRules.length > 0 ? activeRulesHtml : '<li class="p-3 text-gray-500 text-center">No active rules.</li>'}</ul>
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

        const populateValueListbox = () => {
            const sourceColumnSelect = document.getElementById('rule-source-column');
            const selectedColumn = sourceColumnSelect.value;
            const baseHeaders = Object.keys(analysisResults.categoryOverhaulMatrixReport[0] || {});
            const currentDataState = applyOverridesAndMerge(analysisResults.categoryOverhaulMatrixReport, baseHeaders, analysisResults.hasOnsiteData);
            
            const valueSet = new Set();
            let hasBlanks = false;

            currentDataState.forEach(row => {
                const cellValue = row[selectedColumn];
                if (cellValue === null || cellValue === undefined || String(cellValue).trim() === '') {
                    hasBlanks = true;
                } else {
                    String(cellValue).split(' | ').forEach(v => valueSet.add(v.trim()));
                }
            });

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

        const exportBtn = target.closest('.export-btn');
        if (exportBtn) {
            const exportType = exportBtn.dataset.exportType;
            const title = reportContainer ? reportContainer.dataset.reportTitle : 'Report';
            const fileName = title.replace(/[^\w\s]/gi, '').replace(/\s+/g, '_');
            const dataToExport = getFilteredData();
            const headersToExport = updateHeadersForTimeframe(tableState.headers, tableState.timeframe);

            if (title.includes('Category Overhaul Matrix')) {
                // Use the original data from analysisResults instead of the processed data
                const originalData = analysisResults.categoryOverhaulMatrixReport;
                const processedData = applyOverridesAndMerge(originalData, Object.keys(originalData[0] || {}), analysisResults.hasOnsiteData);
                const transformedData = transformDataForTimeframe(processedData, tableState.timeframe);
                
                if (exportType === 'excel') {
                    exportCategoryOverhaulToExcel(transformedData, headersToExport, fileName);
                } else if (exportType === 'json') {
                    exportCategoryOverhaulToJson(transformedData, headersToExport, fileName);
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
                for (let port = 5000; port <= 5010; port++) {
                    try {
                        const response = await fetch(`http://127.0.0.1:${port}/process`, { method: 'POST', body: formData, headers: { 'X-API-KEY': API_KEY }, signal: AbortSignal.timeout(5000) });
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
        pollingInterval = setInterval(async () => {
            try {
                const response = await fetch(`http://127.0.0.1:${port}/status/${taskId}`, { headers: { 'X-API-KEY': API_KEY } });
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
            html += `
            <div class="lens-section">
                <h3 class="text-2xl font-bold mb-4 text-gray-800 border-b pb-2">Content Gaps</h3>
                <p class="text-sm text-gray-600 mb-4">This analysis reveals keywords and topics where your competitors have ranking visibility, but your domain does not. It's designed to uncover new content opportunities and areas where you can expand your digital footprint.</p>
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
                <div class="grid md:grid-cols-2 gap-6">
                    <div data-lens="category-overhaul" class="lens-card p-6 border rounded-lg">
                        <h3 class="font-bold text-xl">Category Overhaul Matrix</h3>
                        <p>Analyse competitor category and facet structures to identify high-traffic taxonomy opportunities and inform site architecture changes.</p>
                    </div>
                    <div data-lens="facet-potential" class="lens-card p-6 border rounded-lg">
                        <h3 class="font-bold text-xl">Facet Potential Analysis</h3>
                        <p>Get a high-level view of which facet <em>types</em> (e.g., Brand, Color) drive the most traffic for each product category.</p>
                    </div>
                </div>
            </div>`;
        }

        html += `</div>`;
        ui.resultsContainer.innerHTML = html;
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

    function renderKeywordGapAnalysisView() {
        const { keywordGapReport, hasOnsiteData, onsiteDateRange } = analysisResults;
        let transformedData = transformDataForTimeframe(keywordGapReport, tableState.timeframe);

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

        const displayHeaders = updateHeadersForTimeframe(headers, tableState.timeframe);

        const displayData = transformedData.map(row => {
            const newRow = {...row};
            const urlHeader = 'Top Competitor URL';
            const urlKeyInRow = Object.keys(newRow).find(k => k.includes(urlHeader));
            if (urlKeyInRow && newRow[urlKeyInRow]) {
                newRow[urlKeyInRow] = `<a href="${newRow[urlKeyInRow]}" target="_blank" class="text-blue-600 hover:underline break-all">${newRow[urlKeyInRow]}</a>`;
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
        const displayHeaders = updateHeadersForTimeframe(headers, tableState.timeframe);

        const displayData = transformedData.map(row => {
            const newRow = {...row};
            const gapCountKey = Object.keys(newRow).find(k => k.includes('Gap Keyword Count'));
            if (gapCountKey) {
                newRow[gapCountKey] = `<button class="text-blue-600 hover:underline view-keywords-btn" data-map-source="${scope}" data-topic-id="${row['TopicID']}">${row[gapCountKey]}</button>`;
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

        const baseHeaders = Object.keys(categoryOverhaulMatrixReport[0] || {});
        
        // Build list of columns to exclude from aggregation (hidden columns)
        const excludeFromAggregation = [];
        if (tableState.hideEntities) {
            excludeFromAggregation.push('Entities', 'Discovered Entities');
        }
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
                    <input type="checkbox" id="hide-entities-column" class="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" ${tableState.hideEntities ? 'checked' : ''}>
                    <label for="hide-entities-column" class="ml-2 block text-sm text-gray-900">Hide Entities column</label>
                </div>
                <div class="flex items-center">
                    <input type="checkbox" id="hide-features-column" class="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" ${tableState.hideFeatures ? 'checked' : ''}>
                    <label for="hide-features-column" class="ml-2 block text-sm text-gray-900">Hide Features column</label>
                </div>
            </div>`;
        
        ui.resultsContainer.innerHTML = createReportContainer('Category Overhaul Matrix', subtitle, customContent, explainer);
        
        // Filter headers based on column visibility state
        let displayHeaders = [...finalHeaders];
        
        if (tableState.hideEntities) {
            displayHeaders = displayHeaders.filter(h => h !== 'Entities' && h !== 'Discovered Entities');
        }
        if (tableState.hideFeatures) {
            displayHeaders = displayHeaders.filter(h => h !== 'Features' && h !== 'Discovered Features');
        }
        
        const defaultSortKey = displayHeaders.find(h => h.includes('Organic Traffic'));
        initializeTable(transformedData, displayHeaders, defaultSortKey, 'Category Mapping');
        
        // Add event listeners for column visibility toggles
        document.getElementById('hide-entities-column')?.addEventListener('change', (e) => {
            tableState.hideEntities = e.target.checked;
            renderCategoryOverhaulMatrixView();
        });
        document.getElementById('hide-features-column')?.addEventListener('change', (e) => {
            tableState.hideFeatures = e.target.checked;
            renderCategoryOverhaulMatrixView();
        });
        tableState.hideZeroTraffic = false; 
        renderOverridesUI(baseHeaders.filter(h => h !== 'KeywordDetails'));
    }

    function renderFacetPotentialAnalysisView() {
        const { categoryOverhaulMatrixReport, hasOnsiteData } = analysisResults;
        
        if (!categoryOverhaulMatrixReport || categoryOverhaulMatrixReport.length === 0) {
            ui.resultsContainer.innerHTML = createReportContainer('Facet Potential Analysis', 'No data available for this report.');
            return;
        }

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

    function initializeTable(data, headers, defaultSortKey, defaultSearchKey, competitorDomains = []) {
        tableState.fullData = data;
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