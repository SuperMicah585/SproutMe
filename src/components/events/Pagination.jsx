import React, { memo, useMemo, useCallback } from 'react';
import { useTheme } from '../../context/ThemeContext';

const Pagination = memo(({ currentPage, totalItems, itemsPerPage, onPageChange }) => {
  const { darkMode } = useTheme();
  
  // Memoize pagination calculations
  const { totalPages, pageNumbers, hasPrevious, hasNext, startPage, endPage } = useMemo(() => {
    const totalPages = Math.ceil(totalItems / itemsPerPage);
    
    // Logic to show limited page numbers with ellipsis
    let startPage = Math.max(1, currentPage - 2);
    let endPage = Math.min(totalPages, currentPage + 2);
    
    // Adjust if we're near the start or end
    if (currentPage <= 3) {
      endPage = Math.min(5, totalPages);
    } else if (currentPage >= totalPages - 2) {
      startPage = Math.max(1, totalPages - 4);
    }
    
    const pageNumbers = Array.from({ length: endPage - startPage + 1 }, (_, i) => startPage + i);
    
    return {
      totalPages,
      pageNumbers,
      hasPrevious: currentPage > 1,
      hasNext: currentPage < totalPages,
      startPage,
      endPage
    };
  }, [currentPage, totalItems, itemsPerPage]);
  
  // Memoize handlers
  const handlePrevious = useCallback(() => {
    if (currentPage > 1) {
      onPageChange(currentPage - 1);
    }
  }, [currentPage, onPageChange]);
  
  const handleNext = useCallback(() => {
    if (currentPage < totalPages) {
      onPageChange(currentPage + 1);
    }
  }, [currentPage, totalPages, onPageChange]);
  
  const handlePageClick = useCallback((page) => {
    onPageChange(page);
  }, [onPageChange]);
  
  // Base button styles
  const buttonBaseClasses = `
    flex items-center justify-center w-10 h-10 rounded-md transition-colors
    ${darkMode 
      ? 'text-gray-300 hover:bg-gray-700' 
      : 'text-gray-700 hover:bg-gray-200'}
  `;
  
  // Active button styles
  const activeButtonClasses = `
    font-bold ${darkMode 
      ? 'bg-green-700 text-white hover:bg-green-600' 
      : 'bg-green-500 text-white hover:bg-green-600'}
  `;
  
  // Disabled button styles
  const disabledButtonClasses = `
    opacity-50 cursor-not-allowed
    ${darkMode ? 'text-gray-600' : 'text-gray-400'}
  `;
  
  return (
    <div className="flex justify-center mt-4">
      <nav className="inline-flex rounded-md shadow-sm" aria-label="Pagination">
        {/* Previous page button */}
        <button
          onClick={handlePrevious}
          disabled={!hasPrevious}
          className={`${buttonBaseClasses} rounded-l-md
            ${!hasPrevious ? disabledButtonClasses : ""}`}
          aria-label="Previous page"
        >
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z"
              clipRule="evenodd"
            />
          </svg>
        </button>
        
        {/* Page number buttons */}
        {/* Show first page and ellipsis if needed */}
        {startPage > 1 && (
          <>
            <button
              onClick={() => handlePageClick(1)}
              className={`${buttonBaseClasses} ${currentPage === 1 ? activeButtonClasses : ""}`}
              aria-label={`Page 1`}
              aria-current={currentPage === 1 ? "page" : undefined}
            >
              1
            </button>
            {startPage > 2 && (
              <span className={`${buttonBaseClasses} cursor-default`}>
                ...
              </span>
            )}
          </>
        )}
        
        {/* Current range of pages */}
        {pageNumbers.map(page => (
          <button
            key={page}
            onClick={() => handlePageClick(page)}
            className={`${buttonBaseClasses} ${currentPage === page ? activeButtonClasses : ""}`}
            aria-label={`Page ${page}`}
            aria-current={currentPage === page ? "page" : undefined}
          >
            {page}
          </button>
        ))}
        
        {/* Show last page and ellipsis if needed */}
        {endPage < totalPages && (
          <>
            {endPage < totalPages - 1 && (
              <span className={`${buttonBaseClasses} cursor-default`}>
                ...
              </span>
            )}
            <button
              onClick={() => handlePageClick(totalPages)}
              className={`${buttonBaseClasses} ${currentPage === totalPages ? activeButtonClasses : ""}`}
              aria-label={`Page ${totalPages}`}
              aria-current={currentPage === totalPages ? "page" : undefined}
            >
              {totalPages}
            </button>
          </>
        )}
        
        {/* Next page button */}
        <button
          onClick={handleNext}
          disabled={!hasNext}
          className={`${buttonBaseClasses} rounded-r-md
            ${!hasNext ? disabledButtonClasses : ""}`}
          aria-label="Next page"
        >
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z"
              clipRule="evenodd"
            />
          </svg>
        </button>
      </nav>
    </div>
  );
}, (prevProps, nextProps) => {
  // Only re-render when these props change
  return (
    prevProps.currentPage === nextProps.currentPage &&
    prevProps.totalItems === nextProps.totalItems &&
    prevProps.itemsPerPage === nextProps.itemsPerPage
  );
});

export default Pagination; 