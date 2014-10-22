library(jsonlite)
library(plyr)
library(futile.logger)
flog.threshold(INFO)
library(ggplot2)

# Flatten the various JSON objects into a single data frame
# Only works well because we happen to know that all the objects
# internally contain a uniform set of keys
flatten_fw_with_type <- function(index, frameworks, framework_names, type) {
  name = framework_names[index]
  flog.debug("Flattening",name,"from",type,"\n")
  
  framework_df = frameworks[[index]]
  if (length(framework_df) == 6)
    framework_df = cbind(framework_df, concurrency = c(8, 16, 32, 64, 128, 256))
  framework_df$framework = name
  framework_df$type = type
  
  flog.debug("Result:\n")
  flog.debug(framework_df)
  return(framework_df);
}

flatten_type <- function(index, types, type_names) {
  name = type_names[index]
  flog.debug("Flattening",name,"\n")
  
  frameworks = types[[index]]
  framework_names = names(frameworks)
  framework_dfs = lapply(seq_along(frameworks), 
         flatten_fw_with_type, frameworks, framework_names, name)
  
  # This is the bit where they have to all have the same columns
  framework_df = do.call(rbind, framework_dfs)
  
  flog.debug("Found",length(framework_dfs),"data frames\nResults:\n")
  flog.debug(framework_df)
  
  return(framework_df)
}

flatten_tfb <- function(resultsFile) {
  json <- fromJSON(readLines(resultsFile))
  flog.info("Reading %s", resultsFile)
  
  types = json$rawData
  type_names = names(types)
  flat_types = lapply(seq_along(types), 
                      flatten_type, types, type_names)
  # They have to all have the same columns
  flat_types = do.call(rbind, flat_types)
  
  # Add in other columns 
  cpu = strsplit(strsplit(resultsFile,'_')[[1]], '-')[[2]][[1]]
  ram = strsplit(strsplit(resultsFile,'_')[[1]], '-')[[3]][[1]]
  flat_types$cpu = cpu
  flat_types$ram = ram
  
  return(flat_types)
}

setwd("~/Research/Docker work (sans C2ORES)/experiment2/results")
flat = lapply(Sys.glob("*/latest/results.json"), flatten_tfb)
flat = ldply(flat, data.frame) # List of DF to one DF
flat$cpu = as.numeric(flat$cpu)
flat$ram = as.numeric(flat$ram)
flat$totalRequests = as.numeric(flat$totalRequests)

# flat$latencyAvg = as.numeric(flat$latencyAvg)
# flat$latencyMax = as.numeric(flat$latencyMax)

d3 <- data.frame(x=rep(flat$cpu, times=500),
                 y=rep(flat$ram, each=500),
                 z=as.vector(flat$totalRequests))
ggplot(d3, aes(x=x, y=y, z=z)) + 
  geom_contour()

ggplot(flat, aes(x=cpu, y=ram, z=totalRequests)) + 
  geom_density2d() + 
  stat_contour() + 
  geom_point()



